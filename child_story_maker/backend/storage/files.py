import os

import requests

from child_story_maker.common.paths import repo_root

MEDIA_DIR = str(repo_root() / "media")

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
SUPABASE_STORAGE_BUCKET = os.getenv("SUPABASE_STORAGE_BUCKET", "")
USE_SUPABASE_STORAGE = bool(
    SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY and SUPABASE_STORAGE_BUCKET
)
DISABLE_LOCAL_MEDIA = os.getenv("DISABLE_LOCAL_MEDIA", "") == "1"


def _supabase_upload(path: str, data: bytes, content_type: str) -> str:
    url = f"{SUPABASE_URL}/storage/v1/object/{SUPABASE_STORAGE_BUCKET}/{path}"
    headers = {
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Content-Type": content_type,
        "x-upsert": "true",
    }
    resp = requests.post(url, headers=headers, data=data, timeout=60)
    if resp.status_code not in (200, 201):
        raise RuntimeError(f"Supabase upload failed: {resp.status_code} {resp.text}")
    return f"{SUPABASE_URL}/storage/v1/object/public/{SUPABASE_STORAGE_BUCKET}/{path}"


def ensure_media_dir() -> None:
    if USE_SUPABASE_STORAGE or DISABLE_LOCAL_MEDIA:
        return
    os.makedirs(MEDIA_DIR, exist_ok=True)


def save_image_bytes(story_id: str, section_id: int, data: bytes) -> str:
    if USE_SUPABASE_STORAGE:
        path = f"{story_id}/sec_{section_id}.png"
        return _supabase_upload(path, data, "image/png")
    folder = os.path.join(MEDIA_DIR, story_id)
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, f"sec_{section_id}.png")
    with open(path, "wb") as f:
        f.write(data)
    return f"/media/{story_id}/sec_{section_id}.png"


def save_audio_bytes(story_id: str, section_id: int, data: bytes, ext: str = "mp3") -> str:
    if USE_SUPABASE_STORAGE:
        path = f"{story_id}/sec_{section_id}.{ext}"
        return _supabase_upload(path, data, f"audio/{ext}")
    folder = os.path.join(MEDIA_DIR, story_id)
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, f"sec_{section_id}.{ext}")
    with open(path, "wb") as f:
        f.write(data)
    return f"/media/{story_id}/sec_{section_id}.{ext}"
