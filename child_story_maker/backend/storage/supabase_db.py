from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import httpx

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "")


def enabled() -> bool:
    return bool(SUPABASE_URL and SUPABASE_ANON_KEY)


def _headers(token: str) -> Dict[str, str]:
    return {
        "apikey": SUPABASE_ANON_KEY,
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }


def _rest_url(path: str) -> str:
    return f"{SUPABASE_URL}/rest/v1/{path.lstrip('/')}"


async def create_story(
    *,
    token: str,
    title: str,
    prompt: str,
    age_group: str,
    language: str,
    style: str,
    child_id: Optional[str],
    sections: List[Dict[str, Any]],
    usage: Optional[Dict[str, Any]] = None,
) -> str:
    if not enabled():
        raise RuntimeError("Supabase is not configured (SUPABASE_URL/SUPABASE_ANON_KEY).")

    story_payload: Dict[str, Any] = {
        "title": title,
        "prompt": prompt,
        "age_group": age_group,
        "language": language,
        "style": style,
    }
    if usage:
        if usage.get("model"):
            story_payload["model"] = usage.get("model")
        if usage.get("input_tokens") is not None:
            story_payload["input_tokens"] = int(usage.get("input_tokens"))
        if usage.get("output_tokens") is not None:
            story_payload["output_tokens"] = int(usage.get("output_tokens"))
        if usage.get("total_tokens") is not None:
            story_payload["total_tokens"] = int(usage.get("total_tokens"))
    if child_id:
        story_payload["child_id"] = child_id

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            _rest_url("stories"),
            headers={**_headers(token), "Prefer": "return=representation"},
            json=story_payload,
        )
        resp.raise_for_status()
        data = resp.json()
        row = data[0] if isinstance(data, list) else data
        story_id = row["id"]

        section_rows = []
        for sec in sections:
            section_rows.append(
                {
                    "story_id": story_id,
                    "idx": int(sec["id"]),
                    "title": sec.get("title") or f"Section {sec['id']}",
                    "text": sec["text"],
                    "image_prompt": sec["image_prompt"],
                    "image_url": sec.get("image_url"),
                    "audio_url": sec.get("audio_url"),
                }
            )
        if section_rows:
            resp2 = await client.post(
                _rest_url("story_sections"),
                headers={**_headers(token), "Prefer": "return=minimal"},
                json=section_rows,
            )
            resp2.raise_for_status()

    return str(story_id)


async def get_story(*, token: str, story_id: str) -> Optional[Dict[str, Any]]:
    if not enabled():
        raise RuntimeError("Supabase is not configured (SUPABASE_URL/SUPABASE_ANON_KEY).")

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            _rest_url("stories"),
            headers=_headers(token),
            params={
                "id": f"eq.{story_id}",
                "select": "id,title,age_group,language,style",
            },
        )
        resp.raise_for_status()
        stories = resp.json() or []
        if not stories:
            return None
        story_row = stories[0]

        resp2 = await client.get(
            _rest_url("story_sections"),
            headers=_headers(token),
            params={
                "story_id": f"eq.{story_id}",
                "select": "idx,title,text,image_prompt,image_url,audio_url",
                "order": "idx.asc",
            },
        )
        resp2.raise_for_status()
        sections = resp2.json() or []

    norm_sections = []
    for sec in sections:
        norm_sections.append(
            {
                "id": int(sec["idx"]),
                "title": sec.get("title") or f"Section {sec['idx']}",
                "text": sec.get("text") or "",
                "image_prompt": sec.get("image_prompt") or "",
                "image_url": sec.get("image_url"),
                "audio_url": sec.get("audio_url"),
            }
        )

    return {
        "title": story_row.get("title") or "Story",
        "sections": norm_sections,
        "status": "ready",
        "age_group": story_row.get("age_group") or "",
        "language": story_row.get("language") or "",
        "style": story_row.get("style") or "",
    }


async def list_stories(
    *, token: str, child_id: Optional[str] = None
) -> List[Dict[str, Any]]:
    if not enabled():
        raise RuntimeError("Supabase is not configured (SUPABASE_URL/SUPABASE_ANON_KEY).")
    params: Dict[str, str] = {
        "select": "id,title,created_at,child_id,age_group,language,style,model,input_tokens,output_tokens,total_tokens",
        "order": "created_at.desc",
    }
    if child_id:
        params["child_id"] = f"eq.{child_id}"
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            _rest_url("stories"),
            headers=_headers(token),
            params=params,
        )
        resp.raise_for_status()
        return resp.json() or []


async def delete_story(*, token: str, story_id: str) -> None:
    if not enabled():
        raise RuntimeError("Supabase is not configured (SUPABASE_URL/SUPABASE_ANON_KEY).")
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.delete(
            _rest_url("stories"),
            headers=_headers(token),
            params={"id": f"eq.{story_id}"},
        )
        resp.raise_for_status()


async def create_share(
    *, token: str, story_id: str, expires_at: Optional[str] = None
) -> str:
    if not enabled():
        raise RuntimeError("Supabase is not configured (SUPABASE_URL/SUPABASE_ANON_KEY).")
    payload: Dict[str, Any] = {"story_id": story_id}
    if expires_at:
        payload["expires_at"] = expires_at
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            _rest_url("story_shares"),
            headers={**_headers(token), "Prefer": "return=representation"},
            json=payload,
        )
        resp.raise_for_status()
        rows = resp.json() or []
        row = rows[0] if rows else {}
        return str(row.get("token", ""))


async def get_story_report(*, token: str, story_id: str) -> Optional[Dict[str, Any]]:
    if not enabled():
        raise RuntimeError("Supabase is not configured (SUPABASE_URL/SUPABASE_ANON_KEY).")
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            _rest_url("story_reports"),
            headers=_headers(token),
            params={"story_id": f"eq.{story_id}", "select": "report"},
        )
        resp.raise_for_status()
        rows = resp.json() or []
        if not rows:
            return None
        return rows[0].get("report")


async def upsert_story_report(
    *, token: str, story_id: str, report: Dict[str, Any]
) -> Dict[str, Any]:
    if not enabled():
        raise RuntimeError("Supabase is not configured (SUPABASE_URL/SUPABASE_ANON_KEY).")
    payload = {"story_id": story_id, "report": report}
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            _rest_url("story_reports"),
            headers={
                **_headers(token),
                "Prefer": "resolution=merge-duplicates,return=representation",
            },
            params={"on_conflict": "story_id"},
            json=payload,
        )
        resp.raise_for_status()
        rows = resp.json() or []
        row = rows[0] if rows else {}
        return row.get("report") or report


async def get_story_learning(
    *, token: str, story_id: str
) -> Optional[Dict[str, Any]]:
    if not enabled():
        raise RuntimeError("Supabase is not configured (SUPABASE_URL/SUPABASE_ANON_KEY).")
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            _rest_url("story_learning"),
            headers=_headers(token),
            params={
                "story_id": f"eq.{story_id}",
                "select": "summary,questions,vocabulary",
            },
        )
        resp.raise_for_status()
        rows = resp.json() or []
        if not rows:
            return None
        return {
            "summary": rows[0].get("summary"),
            "questions": rows[0].get("questions"),
            "vocabulary": rows[0].get("vocabulary"),
        }


async def upsert_story_learning(
    *,
    token: str,
    story_id: str,
    summary: str,
    questions: Any,
    vocabulary: Any,
) -> Dict[str, Any]:
    if not enabled():
        raise RuntimeError("Supabase is not configured (SUPABASE_URL/SUPABASE_ANON_KEY).")
    payload = {
        "story_id": story_id,
        "summary": summary,
        "questions": questions,
        "vocabulary": vocabulary,
    }
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            _rest_url("story_learning"),
            headers={
                **_headers(token),
                "Prefer": "resolution=merge-duplicates,return=representation",
            },
            params={"on_conflict": "story_id"},
            json=payload,
        )
        resp.raise_for_status()
        rows = resp.json() or []
        row = rows[0] if rows else {}
        return {
            "summary": row.get("summary") or summary,
            "questions": row.get("questions") or questions,
            "vocabulary": row.get("vocabulary") or vocabulary,
        }


async def update_section(
    *,
    token: str,
    story_id: str,
    idx: int,
    image_url: Optional[str] = None,
    audio_url: Optional[str] = None,
) -> None:
    if not enabled():
        raise RuntimeError("Supabase is not configured (SUPABASE_URL/SUPABASE_ANON_KEY).")
    patch: Dict[str, Any] = {}
    if image_url is not None:
        patch["image_url"] = image_url
    if audio_url is not None:
        patch["audio_url"] = audio_url
    if not patch:
        return

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.patch(
            _rest_url("story_sections"),
            headers={**_headers(token), "Prefer": "return=minimal"},
            params={"story_id": f"eq.{story_id}", "idx": f"eq.{idx}"},
            json=patch,
        )
        resp.raise_for_status()


async def get_section(*, token: str, story_id: str, idx: int) -> Optional[Dict[str, Any]]:
    if not enabled():
        raise RuntimeError("Supabase is not configured (SUPABASE_URL/SUPABASE_ANON_KEY).")

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            _rest_url("story_sections"),
            headers=_headers(token),
            params={
                "story_id": f"eq.{story_id}",
                "idx": f"eq.{idx}",
                "select": "idx,title,text,image_prompt,image_url,audio_url",
            },
        )
        resp.raise_for_status()
        rows = resp.json() or []
        if not rows:
            return None
        row = rows[0]
    return {
        "id": int(row["idx"]),
        "title": row.get("title") or f"Section {row['idx']}",
        "text": row.get("text") or "",
        "image_prompt": row.get("image_prompt") or "",
        "image_url": row.get("image_url"),
        "audio_url": row.get("audio_url"),
    }
