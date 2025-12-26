# core/story_core.py
from __future__ import annotations

import os
import httpx
import json
import base64
import re
from typing import Any, Dict

from dotenv import load_dotenv
from openai import OpenAI, APIStatusError

from child_story_maker.common.paths import repo_root

load_dotenv(dotenv_path=repo_root() / ".env")

# --- Configuration -----------------------------------------------------------
TEXT_MODEL = os.getenv("STORY_MODEL", "gpt-4o-mini")  # low-cost text model
IMAGE_MODEL = os.getenv("IMAGE_MODEL", "dall-e-2")  # low-cost image model
ALLOW_GPT_IMAGE = os.getenv("ALLOW_GPT_IMAGE", "0").strip() in {"1", "true", "yes"}
DEFAULT_IMAGE_SIZE = os.getenv("IMAGE_SIZE", "512x512")
IMAGE_QUALITY = os.getenv("IMAGE_QUALITY", "low")
IMAGE_FALLBACK_MODELS = [
    m.strip()
    for m in os.getenv("IMAGE_FALLBACK_MODELS", "").split(",")
    if m.strip()
]

if IMAGE_MODEL.lower().startswith("gpt-image-") and not ALLOW_GPT_IMAGE:
    IMAGE_MODEL = "dall-e-2"
    IMAGE_FALLBACK_MODELS = [
        m for m in IMAGE_FALLBACK_MODELS if not m.lower().startswith("gpt-image-")
    ]

SAFE_IMAGE_SUFFIX = (
    "Children's book illustration. Family-friendly, gentle, and wholesome. "
    "Fully clothed characters, modest outfits, and a cheerful tone. "
    "No adult themes, no graphic content, no weapons, no substances. "
    "Non-photorealistic, cartoon or watercolor style."
)

BAD_IMAGE_TERMS = [
    "nude",
    "nudity",
    "naked",
    "lingerie",
    "bikini",
    "swimsuit",
    "swimwear",
    "bathing suit",
    "bra",
    "underwear",
    "cleavage",
    "sexy",
    "erotic",
    "porn",
    "blood",
    "gore",
    "weapon",
    "gun",
    "knife",
    "kill",
    "murder",
    "alcohol",
    "drug",
    "smoking",
    "cigarette",
]

ALLOWED_SIZES_GPT_IMAGE = {"1024x1024", "1024x1536", "1536x1024", "auto"}
ALLOWED_SIZES_DALLE2 = {"256x256", "512x512", "1024x1024"}
ALLOWED_SIZES_DALLE3 = {"1024x1024", "1792x1024", "1024x1792"}
CONTENT_POLICY_MARKERS = ["content_policy", "safety", "rejected", "violation"]
SAFE_GENERIC_PROMPT = (
    "A cheerful children's book illustration of friendly animal characters "
    "wearing colorful clothes, playing in a sunny garden. Soft watercolor style. No text."
)

# Create a single async client (httpx under the hood)
_api_key = os.getenv("OPENAI_API_KEY")
if not _api_key:
    raise RuntimeError("OPENAI_API_KEY missing. Put it in .env")
_client = OpenAI(api_key=_api_key)

# --- Helpers -----------------------------------------------------------------
def _story_schema(sections: int) -> Dict[str, Any]:
    """
    JSON Schema to enforce the model returns exactly the structure your app expects.
    """
    return {
        "name": "Story",
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "title": {"type": "string"},
                "sections": {
                    "type": "array",
                    "minItems": sections,
                    "maxItems": sections,
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "id": {"type": "integer"},
                            "title": {"type": "string"},
                            "text": {"type": "string"},
                            "image_prompt": {"type": "string"},
                        },
                        "required": ["id", "text", "image_prompt"]
                    }
                }
            },
            "required": ["title", "sections"]
        }
    }

def _build_story_prompt(
    *,
    prompt: str,
    age: str,
    language: str,
    style: str,
    sections: int,
    title_hint: str,
) -> str:
    title_line = f"Title hint: {title_hint}\n" if title_hint else ""
    return (
        "You are a children's story generator.\n\n"
        f"Target language: {language}\n"
        f"Target reader age: {age}\n"
        f"Narrative style/tone: {style}\n"
        f"Number of sections/pages: {sections}\n\n"
        f"{title_line}"
        "CONTENT GUIDELINES:\n"
        "- Keep vocabulary appropriate for the target age.\n"
        "- Make each section self-contained and ~3-6 sentences.\n"
        "- Add a few more concrete details in each section while staying age-appropriate.\n"
        "- Gently educational, warm and engaging.\n"
        "- Avoid violence, weapons, blood, alcohol, drugs, or any adult themes.\n"
        "- Give each section a short title.\n"
        "- For each section include an 'image_prompt' that describes a single coherent scene "
        "in a kids-book illustration style (no text overlays), concise but specific.\n"
        "- Image prompts must be kid-safe and fully clothed, no nudity or sexual content.\n\n"
        "STORY IDEA / USER PROMPT:\n"
        f"{prompt}\n\n"
        "OUTPUT FORMAT:\n"
        "Return ONLY valid JSON that matches the provided JSON Schema. Do not include explanations."
    )


def _responses_available(client: OpenAI) -> bool:
    return hasattr(client, "responses")

def _usage_from_response(resp: Any, model: str) -> Dict[str, Any]:
    usage = getattr(resp, "usage", None)
    input_tokens = None
    output_tokens = None
    total_tokens = None
    if usage:
        input_tokens = getattr(usage, "input_tokens", None)
        output_tokens = getattr(usage, "output_tokens", None)
        total_tokens = getattr(usage, "total_tokens", None)
        if input_tokens is None:
            input_tokens = getattr(usage, "prompt_tokens", None)
        if output_tokens is None:
            output_tokens = getattr(usage, "completion_tokens", None)
        if total_tokens is None:
            total_tokens = getattr(usage, "total_tokens", None)
    return {
        "model": getattr(resp, "model", None) or model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
    }

def _image_model_candidates() -> list[str]:
    models = []
    for model in [IMAGE_MODEL] + IMAGE_FALLBACK_MODELS + ["dall-e-2"]:
        if model and model not in models:
            models.append(model)
    if not ALLOW_GPT_IMAGE:
        models = [m for m in models if not m.lower().startswith("gpt-image-")]
    return models

def _download_image(url: str) -> bytes:
    with httpx.Client(timeout=60) as client:
        resp = client.get(url)
        resp.raise_for_status()
    return resp.content


def _sanitize_image_prompt(prompt: str) -> str:
    text = prompt
    for term in BAD_IMAGE_TERMS:
        text = re.sub(rf"\\b{re.escape(term)}\\b", "", text, flags=re.IGNORECASE)
    text = " ".join(text.split())
    return f"{text}. {SAFE_IMAGE_SUFFIX}"


def _is_content_policy_error(err: Exception) -> bool:
    msg = str(err).lower()
    return any(marker in msg for marker in CONTENT_POLICY_MARKERS)


def _call_image_generate(model: str, prompt: str, size: str) -> bytes:
    img = _client.images.generate(
        model=model,
        prompt=prompt,
        size=size,
    )
    if img.data:
        data0 = img.data[0]
        if getattr(data0, "b64_json", None):
            return base64.b64decode(data0.b64_json)
        if getattr(data0, "url", None):
            return _download_image(data0.url)
    raise RuntimeError(f"Image API returned no data for model '{model}'.")


def _normalize_image_size(model: str, size: str) -> str:
    size_norm = (size or "").strip().lower()
    model_norm = (model or "").strip().lower()
    if model_norm.startswith("gpt-image-"):
        return size_norm if size_norm in ALLOWED_SIZES_GPT_IMAGE else "1024x1024"
    if model_norm == "dall-e-2":
        return size_norm if size_norm in ALLOWED_SIZES_DALLE2 else "1024x1024"
    if model_norm == "dall-e-3":
        return size_norm if size_norm in ALLOWED_SIZES_DALLE3 else "1024x1024"
    return size_norm or "1024x1024"

def _split_into_sections(text: str, sections: int) -> list[dict[str, Any]]:
    cleaned = " ".join(text.strip().split())
    if not cleaned:
        return []
    sentences = re.split(r"(?<=[.!?])\s+", cleaned)
    sentences = [s.strip() for s in sentences if s.strip()]
    if not sentences:
        sentences = [cleaned]

    total = len(sentences)
    size = max(1, (total + sections - 1) // sections)
    chunks = []
    idx = 0
    while idx < total:
        chunk = " ".join(sentences[idx : idx + size])
        chunks.append(chunk)
        idx += size
    while len(chunks) < sections:
        chunks.append(chunks[-1])
    if len(chunks) > sections:
        merged = chunks[: sections - 1]
        merged.append(" ".join(chunks[sections - 1 :]))
        chunks = merged

    normalized = []
    for i, text_chunk in enumerate(chunks, start=1):
        normalized.append(
            {
                "id": i,
                "title": f"Section {i}",
                "text": text_chunk,
                "image_prompt": f"Kids book illustration of: {text_chunk[:200]}",
            }
        )
    return normalized


def _safe_json_load(raw_json: str) -> Dict[str, Any]:
    try:
        return json.loads(raw_json)
    except Exception:
        start = raw_json.find("{")
        end = raw_json.rfind("}")
        if start != -1 and end != -1 and end > start:
            return json.loads(raw_json[start : end + 1])
        raise


def _normalize_story_data(
    data: Dict[str, Any], sections: int, *, raw_text: str | None = None
) -> Dict[str, Any]:
    if not isinstance(data, dict):
        raise RuntimeError("Model returned non-object JSON.")

    if "title" not in data:
        data["title"] = "Untitled Story"

    sections_list = None
    if isinstance(data, list):
        sections_list = data
    else:
        story_block = data.get("story")
        if isinstance(story_block, list):
            sections_list = story_block
        elif isinstance(story_block, dict):
            sections_list = (
                story_block.get("sections")
                or story_block.get("chapters")
                or story_block.get("pages")
                or story_block.get("parts")
            )
            if not sections_list and story_block.get("content"):
                sections_list = [story_block.get("content")]

        if not sections_list:
            sections_list = (
                data.get("sections")
                or data.get("chapters")
                or data.get("pages")
                or data.get("parts")
                or data.get("story")
            )

    if not isinstance(sections_list, list) or len(sections_list) < 1:
        fallback_text = ""
        for key in ["text", "story", "content", "output", "body"]:
            val = data.get(key)
            if isinstance(val, str) and val.strip():
                fallback_text = val
                break
        if not fallback_text and raw_text:
            fallback_text = raw_text
        sections_list = _split_into_sections(fallback_text, sections)

    if not isinstance(sections_list, list) or len(sections_list) < 1:
        raise RuntimeError("Model JSON sections must be a non-empty list.")

    normalized = []
    for i, sec in enumerate(sections_list, start=1):
        if isinstance(sec, str):
            text = sec.strip()
            title = f"Section {i}"
            image_prompt = f"Kids book illustration of: {text[:200]}"
            normalized.append(
                {"id": i, "title": title, "text": text, "image_prompt": image_prompt}
            )
            continue

        if not isinstance(sec, dict):
            raise RuntimeError("Model JSON sections must be objects or strings.")

        text = (
            sec.get("text")
            or sec.get("content")
            or sec.get("story")
            or sec.get("body")
            or ""
        ).strip()
        if not text:
            raise RuntimeError("Model JSON sections missing text.")

        if text.startswith("{") or text.startswith("["):
            try:
                nested = _safe_json_load(text)
                nested_sections = None
                if isinstance(nested, dict):
                    nested_sections = (
                        nested.get("sections")
                        or nested.get("chapters")
                        or nested.get("pages")
                        or nested.get("parts")
                        or nested.get("story")
                    )
                if isinstance(nested_sections, list) and nested_sections:
                    combined = []
                    for item in nested_sections:
                        if isinstance(item, dict):
                            combined.append(
                                (item.get("text") or item.get("content") or item.get("story") or "").strip()
                            )
                        elif isinstance(item, str):
                            combined.append(item.strip())
                    combined_text = " ".join(t for t in combined if t)
                    if combined_text:
                        text = combined_text
            except Exception:
                pass

        image_prompt = (
            sec.get("image_prompt")
            or sec.get("imagePrompt")
            or sec.get("illustration_prompt")
            or sec.get("prompt")
            or ""
        ).strip()
        if not image_prompt:
            image_prompt = f"Kids book illustration of: {text[:200]}"

        title = (sec.get("title") or sec.get("heading") or sec.get("name") or "").strip()
        if not title:
            title = f"Section {i}"

        normalized.append(
            {"id": i, "title": title, "text": text, "image_prompt": image_prompt}
        )

    if len(normalized) != sections:
        combined = " ".join(sec["text"] for sec in normalized if sec.get("text"))
        normalized = _split_into_sections(combined, sections)

    data["sections"] = normalized
    return data

# --- Public API --------------------------------------------------------------
async def generate_story_core(
    prompt: str,
    *,
    age: str,
    language: str,
    style: str,
    sections: int,
    title_hint: str = "",
):
    """
    Calls OpenAI Responses API to produce a structured story with json format and 2 main attributes (title and sections, with sections split into 'id','text' and 'image_prompt' ) as follows:
    {
      "title": "...",
      "sections": [
        {"id": 1, "text": "...", "image_prompt": "..."},
        ...
      ]
    }
    """
    # sys_instructions = (
    #     "You generate children's stories and strictly follow JSON schemas. "
    #     "When asked for structured output, you ONLY produce JSON."
    # )
    user_prompt = _build_story_prompt(
        prompt=prompt,
        age=age,
        language=language,
        style=style,
        sections=sections,
        title_hint=title_hint,
    )

    last_error: Exception | None = None
    for attempt in range(2):
        try:
            if _responses_available(_client):
                response_format = (
                    {"type": "json_schema", "json_schema": _story_schema(sections)}
                    if attempt == 0
                    else {"type": "json_object"}
                )
                resp = _client.responses.create(
                    model=TEXT_MODEL,
                    input=user_prompt,
                    response_format=response_format,
                    temperature=0.7 if attempt == 0 else 0.3,
                )
                raw_json = getattr(resp, "output_text", None)
                if not raw_json:
                    output = getattr(resp, "output", []) or []
                    content_items = (output[0].content if output else []) or []
                    raw_json = (
                        getattr(content_items[0], "text", "") if content_items else ""
                    )
            else:
                resp = _client.chat.completions.create(
                    model=TEXT_MODEL,
                    messages=[{"role": "user", "content": user_prompt}],
                    temperature=0.7 if attempt == 0 else 0.3,
                    response_format={"type": "json_object"},
                )
                raw_json = resp.choices[0].message.content

            data = _safe_json_load(raw_json)
            data = _normalize_story_data(data, sections, raw_text=raw_json)
            data["_meta"] = _usage_from_response(resp, TEXT_MODEL)

            if "sections" in data:
                for i, sec in enumerate(data["sections"], start=1):
                    sec["id"] = i
                    if not sec.get("title"):
                        sec["title"] = f"Section {i}"

            return data

        except APIStatusError as e:
            last_error = RuntimeError(
                f"OpenAI API error ({e.status_code}): {e.message}"
            )
        except Exception as e:
            last_error = e

    if last_error:
        raise RuntimeError(f"Failed to generate story: {last_error}") from last_error
    raise RuntimeError("Failed to generate story: unknown error")


async def generate_image_core(image_prompt: str, *, size: str = DEFAULT_IMAGE_SIZE) -> bytes:
    """
    Calls OpenAI Images API and returns PNG bytes for the first generated image.
    """
    safe_prompt = _sanitize_image_prompt(image_prompt)
    last_error: Exception | None = None
    for model in _image_model_candidates():
        size_for_model = _normalize_image_size(model, size)
        try:
            return _call_image_generate(model, safe_prompt, size_for_model)
        except APIStatusError as e:
            if e.status_code == 403 and "verify" in str(e.message).lower():
                if last_error is None:
                    last_error = RuntimeError(
                        f"OpenAI Images API error ({e.status_code}): {e.message}"
                    )
                continue
            if _is_content_policy_error(e):
                try:
                    return _call_image_generate(model, SAFE_GENERIC_PROMPT, size_for_model)
                except Exception as e2:
                    last_error = e2
                    continue
            last_error = RuntimeError(
                f"OpenAI Images API error ({e.status_code}): {e.message}"
            )
        except Exception as e:
            last_error = e

    if _responses_available(_client):
        try:
            response = _client.responses.create(
                model=IMAGE_MODEL,
                input=safe_prompt,
                tools=[
                    {
                        "type": "image_generation",
                        "quality": IMAGE_QUALITY,
                    }
                ],
            )
            for output in response.output or []:
                if getattr(output, "type", "") == "image_generation_call":
                    image_base64 = getattr(output, "result", None)
                    if image_base64:
                        return base64.b64decode(image_base64)
        except APIStatusError as e:
            last_error = RuntimeError(
                f"OpenAI Images API error ({e.status_code}): {e.message}"
            )
        except Exception as e:
            last_error = e

    raise RuntimeError(f"Image generation returned empty result. {last_error}")
