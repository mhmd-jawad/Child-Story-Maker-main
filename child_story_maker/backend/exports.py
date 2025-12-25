from __future__ import annotations

import os
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import httpx

from child_story_maker.common.models import Story, Chapter
from child_story_maker.common.paths import repo_root
from child_story_maker.common.utils import build_pdf, package_story_downloads


def _resolve_media_path(image_url: str) -> Optional[Path]:
    if not image_url:
        return None
    if image_url.startswith("http"):
        parsed = urlparse(image_url)
        if parsed.path.startswith("/media/"):
            return repo_root() / parsed.path.lstrip("/")
        return None
    if image_url.startswith("/media/"):
        return repo_root() / image_url.lstrip("/")
    return None


def _load_image_bytes(image_url: str) -> Optional[bytes]:
    path = _resolve_media_path(image_url)
    if path and path.exists():
        return path.read_bytes()
    if image_url and image_url.startswith("http"):
        try:
            resp = httpx.get(image_url, timeout=30)
            resp.raise_for_status()
            return resp.content
        except Exception:
            return None
    return None


def story_from_db(
    story_id: str, data: dict
) -> Story:
    chapters = []
    for sec in data.get("sections", []):
        image_url = sec.get("image_url")
        chapters.append(
            Chapter(
                title=sec.get("title") or f"Section {sec.get('id', len(chapters) + 1)}",
                text=sec.get("text", ""),
                image_prompt=sec.get("image_prompt"),
                image_url=image_url,
                image_bytes=_load_image_bytes(image_url or ""),
            )
        )
    return Story(
        title=data.get("title", "Untitled Story"),
        author="openai",
        age_group=data.get("age_group", ""),
        language=data.get("language", ""),
        style=data.get("style", ""),
        chapters=chapters,
        story_id=story_id,
    )


def export_zip(story_id: str, data: dict) -> bytes:
    story = story_from_db(story_id, data)
    return package_story_downloads(story)


def export_pdf(story_id: str, data: dict) -> bytes:
    story = story_from_db(story_id, data)
    return build_pdf(story, cover_img_bytes=None)
