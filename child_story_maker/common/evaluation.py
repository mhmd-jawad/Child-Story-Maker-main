from __future__ import annotations

import math
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from child_story_maker.common.models import SAFE_WORDS_BLOCKLIST


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
    "drugs",
    "smoking",
    "cigarette",
]


def build_story_report(
    *,
    story_id: str,
    title: str,
    age_group: str,
    language: str,
    style: str,
    sections: List[Dict[str, Any]],
) -> Dict[str, Any]:
    story_text = "\n\n".join((s.get("text") or "").strip() for s in sections if s)
    image_prompts = "\n".join((s.get("image_prompt") or "").strip() for s in sections if s)

    word_count = _word_count(story_text)
    sentence_count = _sentence_count(story_text)
    fk_grade = _flesch_kincaid_grade(story_text) if _is_english(language) else None

    story_hits = _scan_terms(story_text, _flatten_blocklist(SAFE_WORDS_BLOCKLIST))
    image_hits = _scan_terms(image_prompts, BAD_IMAGE_TERMS)

    return {
        "story_id": story_id,
        "title": title,
        "age_group": age_group,
        "language": language,
        "style": style,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "metrics": {
            "word_count": word_count,
            "sentence_count": sentence_count,
            "avg_sentence_words": (word_count / sentence_count) if sentence_count else None,
            "flesch_kincaid_grade": fk_grade,
        },
        "flags": {
            "blocked_terms_in_story": story_hits,
            "blocked_terms_in_image_prompts": image_hits,
        },
        "notes": [
            "Heuristic report only; not a safety guarantee.",
            "For maximum safety, enable provider moderation and review outputs.",
        ],
    }


def _flatten_blocklist(blocklist: Dict[str, List[str]]) -> List[str]:
    terms: List[str] = []
    for _, items in (blocklist or {}).items():
        for item in items or []:
            val = (item or "").strip()
            if val:
                terms.append(val)
    return terms


def _scan_terms(text: str, terms: List[str]) -> List[str]:
    hits: List[str] = []
    if not text:
        return hits
    for term in terms:
        pattern = _term_pattern(term)
        if not pattern:
            continue
        if re.search(pattern, text, flags=re.IGNORECASE):
            hits.append(term.lower())
    return sorted(set(hits))


def _term_pattern(term: str) -> str:
    term = (term or "").strip()
    if not term:
        return ""
    parts = [re.escape(p) for p in term.split() if p.strip()]
    if not parts:
        return ""
    return r"\b" + r"\s+".join(parts) + r"\b"


def _is_english(language: str) -> bool:
    lang = (language or "").strip().lower()
    if not lang:
        return True
    return lang.startswith("en") or lang.startswith("english")


def _word_count(text: str) -> int:
    words = re.findall(r"[A-Za-z0-9']+", text or "")
    return int(len(words))


def _sentence_count(text: str) -> int:
    chunks = re.split(r"[.!?]+", (text or "").strip())
    chunks = [c.strip() for c in chunks if c.strip()]
    return int(len(chunks))


def _syllable_count(word: str) -> int:
    w = re.sub(r"[^a-z]", "", (word or "").lower())
    if not w:
        return 0
    vowels = "aeiouy"
    count = 0
    prev_vowel = False
    for ch in w:
        is_vowel = ch in vowels
        if is_vowel and not prev_vowel:
            count += 1
        prev_vowel = is_vowel
    if w.endswith("e") and count > 1:
        count -= 1
    return max(count, 1)


def _flesch_kincaid_grade(text: str) -> Optional[float]:
    words = re.findall(r"[A-Za-z0-9']+", text or "")
    if not words:
        return None
    word_count = len(words)
    sentence_count = _sentence_count(text)
    if sentence_count <= 0:
        return None
    syllables = sum(_syllable_count(w) for w in words)
    grade = 0.39 * (word_count / sentence_count) + 11.8 * (syllables / word_count) - 15.59
    return round(float(grade), 2)
