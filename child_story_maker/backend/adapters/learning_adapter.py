from __future__ import annotations

import json
import os
from typing import Any, Dict, List

from dotenv import load_dotenv
from openai import OpenAI, APIStatusError

from child_story_maker.common.paths import repo_root

load_dotenv(dotenv_path=repo_root() / ".env")

LEARNING_MODEL = os.getenv("LEARNING_MODEL", os.getenv("STORY_MODEL", "gpt-4o-mini"))

_api_key = os.getenv("OPENAI_API_KEY")
if not _api_key:
    raise RuntimeError("OPENAI_API_KEY missing. Put it in .env")
_client = OpenAI(api_key=_api_key)


def _responses_available(client: OpenAI) -> bool:
    return hasattr(client, "responses")


def _learning_schema() -> Dict[str, Any]:
    return {
        "name": "LearningPack",
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "summary": {"type": "string"},
                "questions": {
                    "type": "array",
                    "minItems": 3,
                    "maxItems": 5,
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "question": {"type": "string"},
                            "answer": {"type": "string"},
                        },
                        "required": ["question", "answer"],
                    },
                },
                "vocabulary": {
                    "type": "array",
                    "minItems": 3,
                    "maxItems": 8,
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "word": {"type": "string"},
                            "definition": {"type": "string"},
                            "example": {"type": "string"},
                        },
                        "required": ["word", "definition", "example"],
                    },
                },
            },
            "required": ["summary", "questions", "vocabulary"],
        },
    }


def _safe_json_load(raw_json: str) -> Dict[str, Any]:
    try:
        return json.loads(raw_json)
    except Exception:
        start = raw_json.find("{")
        end = raw_json.rfind("}")
        if start != -1 and end != -1 and end > start:
            return json.loads(raw_json[start : end + 1])
        raise


def _trim_text(text: str, max_chars: int = 3200) -> str:
    cleaned = " ".join((text or "").split())
    if len(cleaned) <= max_chars:
        return cleaned
    return cleaned[: max_chars - 1].rstrip() + "…"


def _normalize_learning(data: Dict[str, Any]) -> Dict[str, Any]:
    summary = (data.get("summary") or "").strip()
    questions = data.get("questions") or []
    vocabulary = data.get("vocabulary") or []
    if not isinstance(questions, list):
        questions = []
    if not isinstance(vocabulary, list):
        vocabulary = []
    norm_questions: List[Dict[str, str]] = []
    for q in questions:
        if isinstance(q, dict):
            question = (q.get("question") or "").strip()
            answer = (q.get("answer") or "").strip()
            if question and answer:
                norm_questions.append({"question": question, "answer": answer})
        elif isinstance(q, str) and q.strip():
            norm_questions.append({"question": q.strip(), "answer": ""})
    norm_vocab: List[Dict[str, str]] = []
    for v in vocabulary:
        if isinstance(v, dict):
            word = (v.get("word") or "").strip()
            definition = (v.get("definition") or "").strip()
            example = (v.get("example") or "").strip()
            if word and definition:
                norm_vocab.append(
                    {
                        "word": word,
                        "definition": definition,
                        "example": example or "",
                    }
                )
    return {
        "summary": summary,
        "questions": norm_questions,
        "vocabulary": norm_vocab,
    }


async def generate_learning_pack(
    *,
    title: str,
    age_group: str,
    language: str,
    style: str,
    sections: List[Dict[str, Any]],
) -> Dict[str, Any]:
    story_text = "\n\n".join((s.get("text") or "").strip() for s in sections if s)
    trimmed_text = _trim_text(story_text)
    prompt = (
        "You are a child-friendly educator. Create a learning pack for a short story.\n"
        f"Story title: {title}\n"
        f"Reader age: {age_group}\n"
        f"Language: {language}\n"
        f"Style: {style}\n\n"
        "Return:\n"
        "- A 2-3 sentence summary.\n"
        "- 3-5 comprehension questions with short answers.\n"
        "- 3-6 vocabulary words with kid-friendly definitions and simple examples.\n"
        "Keep everything age-appropriate and gentle.\n\n"
        "STORY TEXT:\n"
        f"{trimmed_text}\n\n"
        "OUTPUT FORMAT: Return ONLY valid JSON that matches the provided JSON schema."
    )

    last_error: Exception | None = None
    for attempt in range(2):
        try:
            if _responses_available(_client):
                response_format = (
                    {"type": "json_schema", "json_schema": _learning_schema()}
                    if attempt == 0
                    else {"type": "json_object"}
                )
                resp = _client.responses.create(
                    model=LEARNING_MODEL,
                    input=prompt,
                    response_format=response_format,
                    temperature=0.4,
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
                    model=LEARNING_MODEL,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.4,
                    response_format={"type": "json_object"},
                )
                raw_json = resp.choices[0].message.content

            data = _safe_json_load(raw_json)
            return _normalize_learning(data)
        except APIStatusError as e:
            last_error = RuntimeError(
                f"OpenAI API error ({e.status_code}): {e.message}"
            )
        except Exception as e:
            last_error = e

    if last_error:
        raise RuntimeError(f"Failed to generate learning pack: {last_error}") from last_error
    raise RuntimeError("Failed to generate learning pack: unknown error")
