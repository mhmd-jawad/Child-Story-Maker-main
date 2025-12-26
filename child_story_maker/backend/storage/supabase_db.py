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
