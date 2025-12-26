from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import httpx

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")


def enabled() -> bool:
    return bool(SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY)


def _headers_admin() -> Dict[str, str]:
    return {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": "application/json",
    }


def _rest_url(path: str) -> str:
    return f"{SUPABASE_URL}/rest/v1/{path.lstrip('/')}"


def _parse_ts(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text)
    except Exception:
        return None


async def get_story_by_share_token(token: str) -> Optional[Dict[str, Any]]:
    if not enabled():
        raise RuntimeError("Supabase admin access is not configured.")

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            _rest_url("story_shares"),
            headers=_headers_admin(),
            params={
                "token": f"eq.{token}",
                "select": "story_id,expires_at",
            },
        )
        resp.raise_for_status()
        shares = resp.json() or []
        if not shares:
            return None
        share = shares[0]
        expires_at = _parse_ts(share.get("expires_at"))
        if expires_at and expires_at < datetime.now(timezone.utc):
            return None
        story_id = share.get("story_id")
        if not story_id:
            return None

        resp2 = await client.get(
            _rest_url("stories"),
            headers=_headers_admin(),
            params={
                "id": f"eq.{story_id}",
                "select": "id,title,age_group,language,style",
            },
        )
        resp2.raise_for_status()
        stories = resp2.json() or []
        if not stories:
            return None
        story_row = stories[0]

        resp3 = await client.get(
            _rest_url("story_sections"),
            headers=_headers_admin(),
            params={
                "story_id": f"eq.{story_id}",
                "select": "idx,title,text,image_prompt,image_url,audio_url",
                "order": "idx.asc",
            },
        )
        resp3.raise_for_status()
        sections = resp3.json() or []

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
        "story_id": str(story_id),
        "title": story_row.get("title") or "Story",
        "sections": norm_sections,
        "status": "ready",
        "age_group": story_row.get("age_group") or "",
        "language": story_row.get("language") or "",
        "style": story_row.get("style") or "",
    }
