import os
import httpx
from dotenv import load_dotenv

from child_story_maker.common.paths import repo_root

load_dotenv(dotenv_path=repo_root() / ".env")
OPENAI_BASE = "https://api.openai.com/v1"

async def synthesize_tts(text: str, *, voice: str = "verse", fmt: str = "mp3") -> bytes:
    """
    Convert text -> speech using OpenAI TTS (gpt-4o-mini-tts).
    Returns raw audio bytes (MP3 by default).
    """
    # gentle pacing for kids: add a period if missing and normalize whitespace
    t = " ".join(text.strip().split())
    if not t.endswith((".", "!", "?")):
        t += "."
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY missing. Put it in .env")
    headers = {"Authorization": f"Bearer {api_key}"}
    body = {"model": "gpt-4o-mini-tts", "voice": voice, "input": t, "format": fmt}
    async with httpx.AsyncClient(timeout=120) as client:
        r = await client.post(f"{OPENAI_BASE}/audio/speech", json=body, headers=headers)
        r.raise_for_status()
        return r.content  # binary audio
