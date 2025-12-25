import os
import requests

from child_story_maker.common.models import Chapter, Story
from child_story_maker.common.utils import reading_level_for_age

API_BASE_URL = os.getenv("STORY_API_BASE_URL", "http://127.0.0.1:8000")
REQUEST_TIMEOUT = 60
IMAGE_SIZE = os.getenv("IMAGE_SIZE", "512x512")


# 1- Story generation: given prompt, title, age_group
def story_generation(
    prompt,
    title_hint,
    age_group,
    language,
    style,
    n_chapters,
    seed,
    extra_context,
    image_style=None,
):
    merged_prompt = prompt
    if extra_context:
        lines = []
        for key, value in extra_context.items():
            if not value:
                continue
            label = key.replace("_", " ").strip().title()
            lines.append(f"- {label}: {value}")
        if lines:
            merged_prompt = f"{prompt}\n\nPersonalization:\n" + "\n".join(lines)

    payload = {
        "prompt": merged_prompt,
        "sections": n_chapters,
        "age": age_group,
        "language": language,
        "style": style,
        "title": title_hint or "",
        "generate_images": False,
    }
    if image_style:
        payload["image_style"] = image_style

    last_error = None
    for _ in range(3):
        try:
            resp = requests.post(
                f"{API_BASE_URL}/story",
                json=payload,
                timeout=REQUEST_TIMEOUT,
            )
            if not resp.ok:
                try:
                    detail = resp.json().get("detail")
                except Exception:
                    detail = resp.text
                raise RuntimeError(
                    f"Story API error {resp.status_code}: {detail}"
                )
            rsj = resp.json()
            break
        except Exception as exc:
            last_error = exc
    else:
        raise RuntimeError(f"Story API failed after retries: {last_error}")

    sections = rsj.get("sections", [])
    chapters = []
    for sec in sections:
        sec_id = sec.get("id", len(chapters) + 1)
        image_url = sec.get("image_url")
        if image_url and image_url.startswith("/"):
            image_url = f"{API_BASE_URL}{image_url}"
        chapters.append(
            Chapter(
                title=sec.get("title") or f"Section {sec_id}",
                text=sec.get("text", ""),
                image_prompt=sec.get("image_prompt"),
                image_url=image_url,
                audio_url=sec.get("audio_url"),
            )
        )

    story = Story(
        title=rsj.get("title", title_hint or "Untitled Story"),
        author="openai",
        age_group=age_group,
        language=language,
        style=style,
        reading_level=reading_level_for_age(age_group),
        chapters=chapters,
        seed=seed,
        story_id=rsj.get("story_id"),
    )
    return story


# 2- Image generation in chat:
def image_generation(title, text, img_style):
    prompt = (
        f"Illustration for the story titled '{title}'. "
        f"Scene: {text}. Style: {img_style}."
    )
    resp = requests.post(
        f"{API_BASE_URL}/image",
        json={"image_prompt": prompt, "size": IMAGE_SIZE},
        timeout=REQUEST_TIMEOUT,
    )
    if not resp.ok:
        try:
            detail = resp.json().get("detail")
        except Exception:
            detail = resp.text
        raise RuntimeError(f"Image API error {resp.status_code}: {detail}")
    data = resp.json()
    image_url = data.get("image_url")
    if not image_url:
        raise RuntimeError("Image API returned no image_url.")
    img_resp = requests.get(f"{API_BASE_URL}{image_url}", timeout=REQUEST_TIMEOUT)
    if not img_resp.ok:
        raise RuntimeError(f"Image download error {img_resp.status_code}: {img_resp.text}")
    return img_resp.content
