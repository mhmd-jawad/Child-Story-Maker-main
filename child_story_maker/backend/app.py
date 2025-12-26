# child_story_maker/backend/app.py
import os
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any

import httpx
from dotenv import load_dotenv

from ..common.paths import repo_root

DOTENV_PATH = repo_root() / ".env"
load_dotenv(dotenv_path=DOTENV_PATH)

from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ConfigDict
from fastapi.responses import Response

from .adapters.core_adapter import (
    generate_story_core,
    generate_image_core,
)
from .adapters.learning_adapter import generate_learning_pack
from .storage.files import (
    ensure_media_dir,
    save_image_bytes,
    save_audio_bytes,
)
from .storage import supabase_db
from .storage import supabase_admin
from .services.tts import synthesize_tts
from .exports import export_zip, export_pdf
from child_story_maker.common.evaluation import build_story_report
from child_story_maker.common.db import (
    init_db,
    create_parent,
    authenticate_parent,
    create_session,
    delete_session,
    get_parent,
    get_parent_id_for_token,
    list_children as db_list_children,
    create_child as db_create_child,
    delete_child as db_delete_child,
)
from child_story_maker.common.utils import kid_safe_prompt


# -------------------------------
# FastAPI app & middleware
# -------------------------------
app = FastAPI(title="Children Storyteller API", version="1.1.0")

# CORS: wide-open for hackathon; restrict origins later if needed
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files for generated media
ensure_media_dir()
media_dir = repo_root() / "media"
if media_dir.exists():
    app.mount("/media", StaticFiles(directory=str(media_dir)), name="media")

USE_LOCAL_DB = os.getenv("USE_LOCAL_DB", "1") == "1"
if USE_LOCAL_DB:
    init_db()


def _require_local_db() -> None:
    if not USE_LOCAL_DB:
        raise HTTPException(
            status_code=501,
            detail="Local auth is disabled. Use Supabase for auth and profiles.",
        )


# -------------------------------
# In-memory "DB" (hackathon-simple)
# story_id -> {"title": str, "sections": [...], "status": str}
# -------------------------------
DB: Dict[str, Dict[str, Any]] = {}
SHARE_DB: Dict[str, Dict[str, Any]] = {}
LEARNING_DB: Dict[str, Dict[str, Any]] = {}
REPORT_DB: Dict[str, Dict[str, Any]] = {}


# -------------------------------
# Pydantic models
# -------------------------------
class SectionResp(BaseModel):
    id: int
    title: Optional[str] = None
    text: str
    image_prompt: str
    image_url: Optional[str] = None
    audio_url: Optional[str] = None


class StoryResp(BaseModel):
    story_id: str
    title: str
    sections: List[SectionResp]
    status: str  # "ready" | "generating-images" | "generating-audio"


class CreateStoryReq(BaseModel):
    prompt: str = Field(min_length=3, max_length=400)
    age: str = Field(default="3-5")
    language: str = Field(default="en", min_length=2, max_length=10)
    style: Optional[str] = Field(default=None, max_length=60)
    sections: int = Field(default=5, ge=1, le=10)
    generate_images: bool = True
    image_size: str = Field(default="512x512", pattern=r"^(auto|\d{2,4}x\d{2,4})$")
    image_style: Optional[str] = Field(default=None, max_length=40)
    title: str = Field(default="")
    child_id: Optional[str] = Field(default=None, max_length=64)
    model_config = ConfigDict(extra="forbid")


class ImagesReq(BaseModel):
    size: str = Field(default="512x512", pattern=r"^(auto|\d{2,4}x\d{2,4})$")
    image_style: Optional[str] = Field(default=None, max_length=40)


class ImageReq(BaseModel):
    image_prompt: str = Field(min_length=3, max_length=800)
    size: str = Field(default="512x512", pattern=r"^(auto|\d{2,4}x\d{2,4})$")
    image_style: Optional[str] = Field(default=None, max_length=40)


class ImageResp(BaseModel):
    image_url: str


class TTSReq(BaseModel):
    voice: str = Field(
        default="verse",
        description="OpenAI built-in voice (e.g., verse, alloy, nova, coral, shimmer)",
    )
    format: str = Field(
        default="mp3",
        pattern=r"^(mp3|wav|aac|flac|opus)$",
        description="Audio file format to save",
    )


class AuthReq(BaseModel):
    email: str = Field(min_length=5, max_length=120)
    password: str = Field(min_length=6, max_length=200)


class AuthResp(BaseModel):
    parent_id: int
    email: str
    token: str


class ChildReq(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    age: int = Field(ge=2, le=12)
    interests: str = Field(min_length=2, max_length=200)


class LearningQuestion(BaseModel):
    question: str = Field(default="", max_length=400)
    answer: str = Field(default="", max_length=400)


class LearningVocab(BaseModel):
    word: str = Field(default="", max_length=80)
    definition: str = Field(default="", max_length=400)
    example: str = Field(default="", max_length=400)


class LearningUpdateReq(BaseModel):
    summary: str = Field(default="", max_length=2000)
    questions: List[LearningQuestion] = Field(default_factory=list)
    vocabulary: List[LearningVocab] = Field(default_factory=list)
    model_config = ConfigDict(extra="forbid")


def _require_parent_id(request: Request) -> int:
    auth = request.headers.get("authorization", "")
    parts = auth.split()
    token = ""
    if len(parts) == 2 and parts[0].lower() == "bearer":
        token = parts[1]
    parent_id = get_parent_id_for_token(token)
    if not parent_id:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return parent_id


def _require_bearer_token(request: Request) -> str:
    auth = request.headers.get("authorization", "")
    parts = auth.split()
    if len(parts) == 2 and parts[0].lower() == "bearer" and parts[1].strip():
        return parts[1].strip()
    raise HTTPException(status_code=401, detail="Unauthorized")


def _build_share_url(request: Request, token: str) -> str:
    base = str(request.base_url).rstrip("/")
    if base.endswith("/api"):
        base = base[: -4]
    return f"{base}/?share={token}"


def _expires_at_from_days(days: Optional[int]) -> Optional[str]:
    if not days:
        return None
    try:
        days_int = int(days)
    except Exception:
        return None
    if days_int <= 0:
        return None
    return (datetime.now(timezone.utc) + timedelta(days=days_int)).isoformat()

# -------------------------------
# Routes
# -------------------------------
@app.get("/health")
def health():
    return {"ok": True}

@app.post("/auth/register", response_model=AuthResp)
def register(req: AuthReq):
    _require_local_db()
    try:
        parent_id = create_parent(req.email, req.password)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    token = create_session(parent_id)
    parent = get_parent(parent_id)
    email = parent["email"] if parent else req.email
    return {"parent_id": parent_id, "email": email, "token": token}


@app.post("/auth/login", response_model=AuthResp)
def login(req: AuthReq):
    _require_local_db()
    parent_id = authenticate_parent(req.email, req.password)
    if not parent_id:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    token = create_session(parent_id)
    parent = get_parent(parent_id)
    email = parent["email"] if parent else req.email
    return {"parent_id": parent_id, "email": email, "token": token}


@app.post("/auth/logout")
def logout(request: Request):
    _require_local_db()
    auth = request.headers.get("authorization", "")
    parts = auth.split()
    token = ""
    if len(parts) == 2 and parts[0].lower() == "bearer":
        token = parts[1]
    delete_session(token)
    return {"ok": True}


@app.get("/auth/me")
def auth_me(parent_id: int = Depends(_require_parent_id)):
    _require_local_db()
    parent = get_parent(parent_id)
    if not parent:
        raise HTTPException(status_code=404, detail="Parent not found")
    return {"parent_id": parent_id, "email": parent["email"]}


@app.get("/children")
def list_children(parent_id: int = Depends(_require_parent_id)):
    _require_local_db()
    rows = db_list_children(parent_id)
    children = [
        {"id": int(r["id"]), "name": r["name"], "age": int(r["age"]), "interests": r["interests"]}
        for r in rows
    ]
    return {"children": children}


@app.post("/children")
def create_child(req: ChildReq, parent_id: int = Depends(_require_parent_id)):
    _require_local_db()
    try:
        child_id = db_create_child(parent_id, req.name, req.age, req.interests)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"id": child_id}


@app.delete("/children/{child_id}")
def delete_child(child_id: int, parent_id: int = Depends(_require_parent_id)):
    _require_local_db()
    db_delete_child(parent_id, child_id)
    return {"ok": True}


@app.post("/story", response_model=StoryResp)
async def create_story(req: CreateStoryReq, request: Request):
    """
    Create a story (and optionally its images).
    """
    ok, err = kid_safe_prompt(req.prompt)
    if not ok:
        raise HTTPException(status_code=400, detail=err)
    use_supabase = (not USE_LOCAL_DB) and supabase_db.enabled()
    token: Optional[str] = _require_bearer_token(request) if use_supabase else None
    try:
        story = await generate_story_core(
            prompt=req.prompt,
            age=req.age,
            language=req.language,
            style=req.style or "default",
            sections=req.sections,
            title_hint=req.title or "",
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Story provider error: {e}")

    try:
        story_meta = story.pop("_meta", {}) if isinstance(story, dict) else {}
        # Normalize sections for the UI layer
        norm_sections: List[Dict[str, Any]] = [
            {
                "id": s["id"],
                "title": s.get("title") or f"Section {s['id']}",
                "text": s["text"],
                "image_prompt": s["image_prompt"],
                "image_url": None,
                "audio_url": None,
            }
            for s in story["sections"]
        ]
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Story response invalid: {e}")

    if use_supabase:
        try:
            story_id = await supabase_db.create_story(
                token=token or "",
                title=req.title.strip() or story["title"],
                prompt=req.prompt,
                age_group=req.age,
                language=req.language,
                style=req.style or "default",
                child_id=req.child_id,
                sections=norm_sections,
                usage=story_meta,
            )
        except httpx.HTTPError as e:
            raise HTTPException(status_code=502, detail=f"Supabase error: {e}") from e
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Supabase error: {e}") from e
        status = "ready"
    else:
        story_id = f"st_{uuid.uuid4().hex[:8]}"
        created_at = datetime.now(timezone.utc).isoformat()
        DB[story_id] = {
            "title": req.title.strip() or story["title"],
            "sections": norm_sections,
            "status": "ready",
            "age_group": req.age,
            "language": req.language,
            "style": req.style or "default",
            "child_id": req.child_id,
            "created_at": created_at,
            "model": story_meta.get("model"),
            "input_tokens": story_meta.get("input_tokens"),
            "output_tokens": story_meta.get("output_tokens"),
            "total_tokens": story_meta.get("total_tokens"),
        }
        status = "ready"

    if req.generate_images:
        if not use_supabase:
            DB[story_id]["status"] = "generating-images"
        try:
            for s in norm_sections:
                prompt = s["image_prompt"]
                if req.image_style:
                    prompt = f"{prompt}. Style: {req.image_style}."
                img_bytes = await generate_image_core(prompt, size=req.image_size)
                s["image_url"] = save_image_bytes(story_id, s["id"], img_bytes)
                if use_supabase:
                    await supabase_db.update_section(
                        token=token or "",
                        story_id=story_id,
                        idx=int(s["id"]),
                        image_url=s["image_url"],
                    )
        except Exception as e:
            if not use_supabase:
                DB[story_id]["status"] = "ready"  # fail soft; client can retry images
            raise HTTPException(status_code=502, detail=f"Image provider error: {e}")
        if not use_supabase:
            DB[story_id]["status"] = "ready"

    return {
        "story_id": story_id,
        "title": (DB[story_id]["title"] if not use_supabase else (req.title.strip() or story["title"])),
        "sections": (DB[story_id]["sections"] if not use_supabase else norm_sections),
        "status": (DB[story_id]["status"] if not use_supabase else status),
    }


@app.get("/story/{story_id}", response_model=StoryResp)
async def get_story(story_id: str, request: Request):
    use_supabase = (not USE_LOCAL_DB) and supabase_db.enabled()
    if use_supabase:
        token = _require_bearer_token(request)
        data = await supabase_db.get_story(token=token, story_id=story_id)
        if not data:
            raise HTTPException(status_code=404, detail="Story not found")
        return {
            "story_id": story_id,
            "title": data["title"],
            "sections": data["sections"],
            "status": data["status"],
        }

    data = DB.get(story_id)
    if not data:
        raise HTTPException(status_code=404, detail="Story not found")
    return {
        "story_id": story_id,
        "title": data["title"],
        "sections": data["sections"],
        "status": data["status"],
    }


@app.get("/stories")
async def list_stories(request: Request, child_id: Optional[str] = None):
    use_supabase = (not USE_LOCAL_DB) and supabase_db.enabled()
    if use_supabase:
        token = _require_bearer_token(request)
        rows = await supabase_db.list_stories(token=token, child_id=child_id)
        stories = [
            {
                "story_id": r.get("id"),
                "title": r.get("title"),
                "created_at": r.get("created_at"),
                "child_id": r.get("child_id"),
                "age_group": r.get("age_group"),
                "language": r.get("language"),
                "style": r.get("style"),
                "model": r.get("model"),
                "input_tokens": r.get("input_tokens"),
                "output_tokens": r.get("output_tokens"),
                "total_tokens": r.get("total_tokens"),
            }
            for r in (rows or [])
        ]
        return {"stories": stories}

    stories = []
    for story_id, data in DB.items():
        if child_id and str(data.get("child_id")) != str(child_id):
            continue
        stories.append(
            {
                "story_id": story_id,
                "title": data.get("title"),
                "created_at": data.get("created_at"),
                "child_id": data.get("child_id"),
                "age_group": data.get("age_group"),
                "language": data.get("language"),
                "style": data.get("style"),
                "model": data.get("model"),
                "input_tokens": data.get("input_tokens"),
                "output_tokens": data.get("output_tokens"),
                "total_tokens": data.get("total_tokens"),
            }
        )
    stories.sort(key=lambda s: s.get("created_at") or "", reverse=True)
    return {"stories": stories}


@app.delete("/story/{story_id}")
async def delete_story(story_id: str, request: Request):
    use_supabase = (not USE_LOCAL_DB) and supabase_db.enabled()
    if use_supabase:
        token = _require_bearer_token(request)
        await supabase_db.delete_story(token=token, story_id=story_id)
        return {"ok": True}
    if story_id in DB:
        DB.pop(story_id, None)
        for token, share in list(SHARE_DB.items()):
            if share.get("story_id") == story_id:
                SHARE_DB.pop(token, None)
        LEARNING_DB.pop(story_id, None)
        REPORT_DB.pop(story_id, None)
        return {"ok": True}
    raise HTTPException(status_code=404, detail="Story not found")


@app.post("/story/{story_id}/share")
async def create_share(story_id: str, request: Request, expires_in_days: Optional[int] = None):
    use_supabase = (not USE_LOCAL_DB) and supabase_db.enabled()
    expires_at = _expires_at_from_days(expires_in_days)
    if use_supabase:
        token = _require_bearer_token(request)
        share_token = await supabase_db.create_share(
            token=token, story_id=story_id, expires_at=expires_at
        )
        if not share_token:
            raise HTTPException(status_code=502, detail="Failed to create share token.")
        return {
            "token": share_token,
            "share_url": _build_share_url(request, share_token),
        }

    if story_id not in DB:
        raise HTTPException(status_code=404, detail="Story not found")
    share_token = uuid.uuid4().hex
    SHARE_DB[share_token] = {"story_id": story_id, "expires_at": expires_at}
    return {"token": share_token, "share_url": _build_share_url(request, share_token)}


@app.get("/share/{token}", response_model=StoryResp)
async def get_share_story(token: str):
    use_supabase = (not USE_LOCAL_DB) and supabase_db.enabled()
    if use_supabase:
        if not supabase_admin.enabled():
            raise HTTPException(status_code=503, detail="Share access not configured.")
        data = await supabase_admin.get_story_by_share_token(token)
        if not data:
            raise HTTPException(status_code=404, detail="Share not found")
        return {
            "story_id": data["story_id"],
            "title": data["title"],
            "sections": data["sections"],
            "status": data["status"],
        }

    share = SHARE_DB.get(token)
    if not share:
        raise HTTPException(status_code=404, detail="Share not found")
    expires_at = share.get("expires_at")
    if expires_at:
        try:
            if datetime.fromisoformat(expires_at) < datetime.now(timezone.utc):
                raise HTTPException(status_code=404, detail="Share expired")
        except ValueError:
            pass
    story_id = share.get("story_id")
    data = DB.get(story_id)
    if not data:
        raise HTTPException(status_code=404, detail="Story not found")
    return {
        "story_id": story_id,
        "title": data["title"],
        "sections": data["sections"],
        "status": data["status"],
    }


@app.get("/share/{token}/export/zip")
async def export_share_zip(token: str):
    use_supabase = (not USE_LOCAL_DB) and supabase_db.enabled()
    if use_supabase:
        if not supabase_admin.enabled():
            raise HTTPException(status_code=503, detail="Share access not configured.")
        data = await supabase_admin.get_story_by_share_token(token)
        if not data:
            raise HTTPException(status_code=404, detail="Share not found")
    else:
        share = SHARE_DB.get(token)
        if not share:
            raise HTTPException(status_code=404, detail="Share not found")
        data = DB.get(share.get("story_id"))
        if not data:
            raise HTTPException(status_code=404, detail="Story not found")

    story_id = data.get("story_id") if isinstance(data, dict) else None
    if not story_id and not use_supabase:
        story_id = share.get("story_id")
    zip_bytes = export_zip(story_id or "shared_story", data)
    filename = f"{data.get('title', 'story').replace(' ', '_').lower()}_story.zip"
    return Response(
        zip_bytes,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@app.get("/share/{token}/export/pdf")
async def export_share_pdf(token: str):
    use_supabase = (not USE_LOCAL_DB) and supabase_db.enabled()
    if use_supabase:
        if not supabase_admin.enabled():
            raise HTTPException(status_code=503, detail="Share access not configured.")
        data = await supabase_admin.get_story_by_share_token(token)
        if not data:
            raise HTTPException(status_code=404, detail="Share not found")
    else:
        share = SHARE_DB.get(token)
        if not share:
            raise HTTPException(status_code=404, detail="Share not found")
        data = DB.get(share.get("story_id"))
        if not data:
            raise HTTPException(status_code=404, detail="Story not found")

    story_id = data.get("story_id") if isinstance(data, dict) else None
    if not story_id and not use_supabase:
        story_id = share.get("story_id")
    pdf_bytes = export_pdf(story_id or "shared_story", data)
    filename = f"{data.get('title', 'story').replace(' ', '_').lower()}.pdf"
    return Response(
        pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@app.get("/story/{story_id}/report")
async def story_report(story_id: str, request: Request, refresh: bool = False):
    use_supabase = (not USE_LOCAL_DB) and supabase_db.enabled()
    data = None
    if use_supabase:
        token = _require_bearer_token(request)
        if not refresh:
            existing = await supabase_db.get_story_report(token=token, story_id=story_id)
            if existing:
                return existing
        data = await supabase_db.get_story(token=token, story_id=story_id)
    else:
        if not refresh and story_id in REPORT_DB:
            return REPORT_DB[story_id]
        data = DB.get(story_id)

    if not data:
        raise HTTPException(status_code=404, detail="Story not found")

    report = build_story_report(
        story_id=story_id,
        title=data.get("title", "Story"),
        age_group=data.get("age_group", ""),
        language=data.get("language", ""),
        style=data.get("style", ""),
        sections=data.get("sections", []),
    )
    if use_supabase:
        await supabase_db.upsert_story_report(token=token, story_id=story_id, report=report)
    else:
        REPORT_DB[story_id] = report
    return report


@app.get("/story/{story_id}/learning")
async def get_learning(story_id: str, request: Request):
    use_supabase = (not USE_LOCAL_DB) and supabase_db.enabled()
    if use_supabase:
        token = _require_bearer_token(request)
        learning = await supabase_db.get_story_learning(token=token, story_id=story_id)
        if not learning:
            raise HTTPException(status_code=404, detail="Learning pack not found")
        return learning

    learning = LEARNING_DB.get(story_id)
    if not learning:
        raise HTTPException(status_code=404, detail="Learning pack not found")
    return learning


@app.post("/story/{story_id}/learning")
async def generate_learning(story_id: str, request: Request, refresh: bool = False):
    use_supabase = (not USE_LOCAL_DB) and supabase_db.enabled()
    data = None
    if use_supabase:
        token = _require_bearer_token(request)
        if not refresh:
            existing = await supabase_db.get_story_learning(token=token, story_id=story_id)
            if existing:
                return existing
        data = await supabase_db.get_story(token=token, story_id=story_id)
    else:
        if not refresh and story_id in LEARNING_DB:
            return LEARNING_DB[story_id]
        data = DB.get(story_id)

    if not data:
        raise HTTPException(status_code=404, detail="Story not found")

    try:
        learning = await generate_learning_pack(
            title=data.get("title", "Story"),
            age_group=data.get("age_group", ""),
            language=data.get("language", ""),
            style=data.get("style", ""),
            sections=data.get("sections", []),
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Learning provider error: {e}")

    if use_supabase:
        await supabase_db.upsert_story_learning(
            token=token,
            story_id=story_id,
            summary=learning.get("summary", ""),
            questions=learning.get("questions", []),
            vocabulary=learning.get("vocabulary", []),
        )
    else:
        LEARNING_DB[story_id] = learning
    return learning


@app.post("/story/{story_id}/learning/manual")
async def save_learning_manual(
    story_id: str, req: LearningUpdateReq, request: Request
):
    use_supabase = (not USE_LOCAL_DB) and supabase_db.enabled()
    if use_supabase:
        token = _require_bearer_token(request)
        data = await supabase_db.get_story(token=token, story_id=story_id)
        if not data:
            raise HTTPException(status_code=404, detail="Story not found")
        learning = {
            "summary": (req.summary or "").strip(),
            "questions": [q.model_dump() for q in req.questions],
            "vocabulary": [v.model_dump() for v in req.vocabulary],
        }
        await supabase_db.upsert_story_learning(
            token=token,
            story_id=story_id,
            summary=learning["summary"],
            questions=learning["questions"],
            vocabulary=learning["vocabulary"],
        )
        return learning

    if story_id not in DB:
        raise HTTPException(status_code=404, detail="Story not found")
    learning = {
        "summary": (req.summary or "").strip(),
        "questions": [q.model_dump() for q in req.questions],
        "vocabulary": [v.model_dump() for v in req.vocabulary],
    }
    LEARNING_DB[story_id] = learning
    return learning


@app.get("/story/{story_id}/export/zip")
async def export_story_zip(story_id: str, request: Request):
    use_supabase = (not USE_LOCAL_DB) and supabase_db.enabled()
    if use_supabase:
        token = _require_bearer_token(request)
        data = await supabase_db.get_story(token=token, story_id=story_id)
        if not data:
            raise HTTPException(status_code=404, detail="Story not found")
    else:
        data = DB.get(story_id)
        if not data:
            raise HTTPException(status_code=404, detail="Story not found")

    zip_bytes = export_zip(story_id, data)
    filename = f"{data.get('title', 'story').replace(' ', '_').lower()}_story.zip"
    return Response(
        zip_bytes,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@app.get("/story/{story_id}/export/pdf")
async def export_story_pdf(story_id: str, request: Request):
    use_supabase = (not USE_LOCAL_DB) and supabase_db.enabled()
    if use_supabase:
        token = _require_bearer_token(request)
        data = await supabase_db.get_story(token=token, story_id=story_id)
        if not data:
            raise HTTPException(status_code=404, detail="Story not found")
    else:
        data = DB.get(story_id)
        if not data:
            raise HTTPException(status_code=404, detail="Story not found")

    pdf_bytes = export_pdf(story_id, data)
    filename = f"{data.get('title', 'story').replace(' ', '_').lower()}.pdf"
    return Response(
        pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@app.post("/story/{story_id}/images", response_model=StoryResp)
async def generate_images(story_id: str, req: ImagesReq, request: Request):
    """
    (Re)generate images for each section.
    """
    use_supabase = (not USE_LOCAL_DB) and supabase_db.enabled()
    token: Optional[str] = _require_bearer_token(request) if use_supabase else None
    if use_supabase:
        d = await supabase_db.get_story(token=token or "", story_id=story_id)
        if not d:
            raise HTTPException(status_code=404, detail="Story not found")
    else:
        d = DB.get(story_id)
        if not d:
            raise HTTPException(status_code=404, detail="Story not found")
        d["status"] = "generating-images"
    try:
        for s in d["sections"]:
            prompt = s["image_prompt"]
            if req.image_style:
                prompt = f"{prompt}. Style: {req.image_style}."
            img_bytes = await generate_image_core(prompt, size=req.size)
            s["image_url"] = save_image_bytes(story_id, s["id"], img_bytes)
            if use_supabase:
                await supabase_db.update_section(
                    token=token or "",
                    story_id=story_id,
                    idx=int(s["id"]),
                    image_url=s["image_url"],
                )
    except Exception as e:
        if not use_supabase:
            d["status"] = "ready"
        raise HTTPException(status_code=502, detail=f"Image provider error: {e}")

    if not use_supabase:
        d["status"] = "ready"
    return {
        "story_id": story_id,
        "title": d["title"],
        "sections": d["sections"],
        "status": "ready",
    }


@app.post("/story/{story_id}/sections/{section_id}/image", response_model=SectionResp)
async def generate_section_image(
    story_id: str, section_id: int, req: ImagesReq, request: Request
):
    """
    Generate (or regenerate) a single section image.
    Useful for serverless deployments to avoid long-running requests.
    """
    use_supabase = (not USE_LOCAL_DB) and supabase_db.enabled()
    token: Optional[str] = _require_bearer_token(request) if use_supabase else None

    if use_supabase:
        section = await supabase_db.get_section(token=token or "", story_id=story_id, idx=section_id)
        if not section:
            raise HTTPException(status_code=404, detail="Section not found")
    else:
        story = DB.get(story_id)
        if not story:
            raise HTTPException(status_code=404, detail="Story not found")
        section = next((s for s in story["sections"] if int(s["id"]) == int(section_id)), None)
        if not section:
            raise HTTPException(status_code=404, detail="Section not found")

    prompt = section["image_prompt"]
    if req.image_style:
        prompt = f"{prompt}. Style: {req.image_style}."
    try:
        img_bytes = await generate_image_core(prompt, size=req.size)
        image_url = save_image_bytes(story_id, int(section_id), img_bytes)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Image provider error: {e}")

    section["image_url"] = image_url
    if use_supabase:
        await supabase_db.update_section(
            token=token or "",
            story_id=story_id,
            idx=int(section_id),
            image_url=image_url,
        )

    return section


@app.post("/image", response_model=ImageResp)
async def generate_image(req: ImageReq):
    """
    Generate a single image from a prompt and return a media URL.
    """
    prompt = req.image_prompt
    if req.image_style:
        prompt = f"{prompt}. Style: {req.image_style}."
    try:
        img_bytes = await generate_image_core(prompt, size=req.size)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Image provider error: {e}")

    if not isinstance(img_bytes, (bytes, bytearray)):
        raise HTTPException(status_code=502, detail="Image provider returned no data.")

    image_id = f"img_{uuid.uuid4().hex[:8]}"
    try:
        image_url = save_image_bytes(image_id, 0, img_bytes)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Image save error: {e}")
    return {"image_url": image_url}


@app.post("/story/{story_id}/tts", response_model=StoryResp)
async def generate_tts(story_id: str, req: TTSReq, request: Request):
    """
    Generate audio for each section and return updated story.
    """
    use_supabase = (not USE_LOCAL_DB) and supabase_db.enabled()
    token: Optional[str] = _require_bearer_token(request) if use_supabase else None
    if use_supabase:
        d = await supabase_db.get_story(token=token or "", story_id=story_id)
        if not d:
            raise HTTPException(status_code=404, detail="Story not found")
    else:
        d = DB.get(story_id)
        if not d:
            raise HTTPException(status_code=404, detail="Story not found")
        d["status"] = "generating-audio"
    try:
        for s in d["sections"]:
            audio_bytes = await synthesize_tts(
                s["text"], voice=req.voice, fmt=req.format
            )
            s["audio_url"] = save_audio_bytes(
                story_id, s["id"], audio_bytes, ext=req.format
            )
            if use_supabase:
                await supabase_db.update_section(
                    token=token or "",
                    story_id=story_id,
                    idx=int(s["id"]),
                    audio_url=s["audio_url"],
                )
    except Exception as e:
        if not use_supabase:
            d["status"] = "ready"
        raise HTTPException(status_code=502, detail=f"TTS provider error: {e}")

    if not use_supabase:
        d["status"] = "ready"
    return {
        "story_id": story_id,
        "title": d["title"],
        "sections": d["sections"],
        "status": "ready",
    }


# Serve the web UI (mount last so it doesn't shadow API routes)
WEB_DIR = repo_root() / "web"
if WEB_DIR.exists():
    app.mount("/", StaticFiles(directory=str(WEB_DIR), html=True), name="web")
