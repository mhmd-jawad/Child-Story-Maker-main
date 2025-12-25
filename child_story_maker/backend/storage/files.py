import os

from child_story_maker.common.paths import repo_root

MEDIA_DIR = str(repo_root() / "media")

def ensure_media_dir() -> None:
    os.makedirs(MEDIA_DIR, exist_ok=True)

def save_image_bytes(story_id: str, section_id: int, data: bytes) -> str:
    folder = os.path.join(MEDIA_DIR, story_id)
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, f"sec_{section_id}.png")
    with open(path, "wb") as f:
        f.write(data)
    return f"/media/{story_id}/sec_{section_id}.png"

def save_audio_bytes(story_id: str, section_id: int, data: bytes, ext: str = "mp3") -> str:
    folder = os.path.join(MEDIA_DIR, story_id)
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, f"sec_{section_id}.{ext}")
    with open(path, "wb") as f:
        f.write(data)
    return f"/media/{story_id}/sec_{section_id}.{ext}"
