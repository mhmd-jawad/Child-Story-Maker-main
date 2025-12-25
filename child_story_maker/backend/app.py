# child_story_maker/backend/app.py
import uuid
from typing import Optional, List, Dict, Any

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
from .storage.files import (
    ensure_media_dir,
    save_image_bytes,
    save_audio_bytes,
)
from .services.tts import synthesize_tts
from .exports import export_zip, export_pdf
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
app.mount("/media", StaticFiles(directory=str(repo_root() / "media")), name="media")

init_db()


# -------------------------------
# In-memory "DB" (hackathon-simple)
# story_id -> {"title": str, "sections": [...], "status": str}
# -------------------------------
DB: Dict[str, Dict[str, Any]] = {}


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

# -------------------------------
# Routes
# -------------------------------
@app.get("/health")
def health():
    return {"ok": True}

@app.post("/auth/register", response_model=AuthResp)
def register(req: AuthReq):
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
    parent_id = authenticate_parent(req.email, req.password)
    if not parent_id:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    token = create_session(parent_id)
    parent = get_parent(parent_id)
    email = parent["email"] if parent else req.email
    return {"parent_id": parent_id, "email": email, "token": token}


@app.post("/auth/logout")
def logout(request: Request):
    auth = request.headers.get("authorization", "")
    parts = auth.split()
    token = ""
    if len(parts) == 2 and parts[0].lower() == "bearer":
        token = parts[1]
    delete_session(token)
    return {"ok": True}


@app.get("/auth/me")
def auth_me(parent_id: int = Depends(_require_parent_id)):
    parent = get_parent(parent_id)
    if not parent:
        raise HTTPException(status_code=404, detail="Parent not found")
    return {"parent_id": parent_id, "email": parent["email"]}


@app.get("/children")
def list_children(parent_id: int = Depends(_require_parent_id)):
    rows = db_list_children(parent_id)
    children = [
        {"id": int(r["id"]), "name": r["name"], "age": int(r["age"]), "interests": r["interests"]}
        for r in rows
    ]
    return {"children": children}


@app.post("/children")
def create_child(req: ChildReq, parent_id: int = Depends(_require_parent_id)):
    try:
        child_id = db_create_child(parent_id, req.name, req.age, req.interests)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"id": child_id}


@app.delete("/children/{child_id}")
def delete_child(child_id: int, parent_id: int = Depends(_require_parent_id)):
    db_delete_child(parent_id, child_id)
    return {"ok": True}


@app.post("/story", response_model=StoryResp)
async def create_story(req: CreateStoryReq):
    """
    Create a story (and optionally its images).
    """
    ok, err = kid_safe_prompt(req.prompt)
    if not ok:
        raise HTTPException(status_code=400, detail=err)
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

    story_id = f"st_{uuid.uuid4().hex[:8]}"

    try:
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

    DB[story_id] = {
        "title": req.title.strip() or story["title"],
        "sections": norm_sections,
        "status": "ready",
        "age_group": req.age,
        "language": req.language,
        "style": req.style or "default",
    }

    if req.generate_images:
        DB[story_id]["status"] = "generating-images"
        try:
            for s in norm_sections:
                prompt = s["image_prompt"]
                if req.image_style:
                    prompt = f"{prompt}. Style: {req.image_style}."
                img_bytes = await generate_image_core(prompt, size=req.image_size)
                s["image_url"] = save_image_bytes(story_id, s["id"], img_bytes)
        except Exception as e:
            DB[story_id]["status"] = "ready"  # fail soft; client can retry images
            raise HTTPException(status_code=502, detail=f"Image provider error: {e}")
        DB[story_id]["status"] = "ready"

    return {
        "story_id": story_id,
        "title": DB[story_id]["title"],
        "sections": DB[story_id]["sections"],
        "status": DB[story_id]["status"],
    }


@app.get("/story/{story_id}", response_model=StoryResp)
def get_story(story_id: str):
    data = DB.get(story_id)
    if not data:
        raise HTTPException(status_code=404, detail="Story not found")
    return {
        "story_id": story_id,
        "title": data["title"],
        "sections": data["sections"],
        "status": data["status"],
    }


@app.get("/story/{story_id}/export/zip")
def export_story_zip(story_id: str):
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
def export_story_pdf(story_id: str):
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
async def generate_images(story_id: str, req: ImagesReq):
    """
    (Re)generate images for each section.
    """
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
    except Exception as e:
        d["status"] = "ready"
        raise HTTPException(status_code=502, detail=f"Image provider error: {e}")

    d["status"] = "ready"
    return {
        "story_id": story_id,
        "title": d["title"],
        "sections": d["sections"],
        "status": d["status"],
    }


# Serve the web UI
WEB_DIR = repo_root() / "web"
if WEB_DIR.exists():
    app.mount("/", StaticFiles(directory=str(WEB_DIR), html=True), name="web")


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
async def generate_tts(story_id: str, req: TTSReq):
    """
    Generate audio for each section and return updated story.
    """
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
    except Exception as e:
        d["status"] = "ready"
        raise HTTPException(status_code=502, detail=f"TTS provider error: {e}")

    d["status"] = "ready"
    return {
        "story_id": story_id,
        "title": d["title"],
        "sections": d["sections"],
        "status": d["status"],
    }
