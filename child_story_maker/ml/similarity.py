from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List

from ..common.paths import repo_root

DEFAULT_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
DEFAULT_EMB_FILE = repo_root() / "artifacts" / "embeddings" / "children_books_embeddings.npy"
DEFAULT_AVG_FILE = repo_root() / "artifacts" / "embeddings" / "children_books_avg_embedding.npy"
DEFAULT_INDEX_FILE = repo_root() / "artifacts" / "embeddings" / "children_books_index.json"
DEFAULT_THRESHOLD = 0.25


@dataclass
class SimilarityHit:
    idx: int
    score: float
    title: str
    author: str
    preview: str
    interest_age: str
    reading_age: str


@dataclass
class SimilarityResult:
    similarity_to_average: float
    is_child_like: bool
    top_k: List[SimilarityHit]
    stats: Dict[str, Any]
    model_name: str


def _require_deps():
    try:
        import numpy as np
        from sentence_transformers import SentenceTransformer
    except Exception as exc:
        raise RuntimeError(
            "Embeddings dependencies missing. Install requirements-embeddings.txt."
        ) from exc
    return np, SentenceTransformer


@lru_cache(maxsize=1)
def _load_model(model_name: str):
    _, SentenceTransformer = _require_deps()
    return SentenceTransformer(model_name)


@lru_cache(maxsize=1)
def _load_artifacts(
    emb_path: str, avg_path: str, index_path: str
) -> tuple[Any, Any, Dict[str, Any]]:
    np, _ = _require_deps()
    emb_file = Path(emb_path)
    idx_file = Path(index_path)
    avg_file = Path(avg_path)

    missing = [str(p) for p in [emb_file, idx_file] if not p.exists()]
    if missing:
        raise FileNotFoundError(
            "Missing embedding artifacts. Run `python -m child_story_maker.ml.build_embeddings` to build: "
            + ", ".join(missing)
        )

    embeddings = np.load(emb_file)
    if embeddings.ndim != 2:
        raise ValueError("Embeddings file has unexpected shape.")
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    embeddings = embeddings / norms

    if avg_file.exists():
        avg_vec = np.load(avg_file)
    else:
        avg_vec = embeddings.mean(axis=0)
        norm = np.linalg.norm(avg_vec)
        if norm > 0:
            avg_vec = avg_vec / norm

    index = {}
    try:
        index = json_load(idx_file)
    except Exception:
        index = {}

    return embeddings, avg_vec, index


def compare_text(
    text: str,
    *,
    k: int = 5,
    threshold: float = DEFAULT_THRESHOLD,
    model_name: str = DEFAULT_MODEL_NAME,
    emb_path: Path = DEFAULT_EMB_FILE,
    avg_path: Path = DEFAULT_AVG_FILE,
    index_path: Path = DEFAULT_INDEX_FILE,
) -> SimilarityResult:
    np, _ = _require_deps()
    embeddings, avg_vec, index = _load_artifacts(
        str(emb_path), str(avg_path), str(index_path)
    )
    model = _load_model(model_name)

    q = model.encode([text], convert_to_numpy=True, normalize_embeddings=True)
    sims = embeddings @ q.T
    sims = sims.ravel()
    if len(sims) == 0:
        raise ValueError("Embeddings index is empty.")
    k_eff = int(min(max(k, 1), len(sims)))
    idx = np.argpartition(-sims, range(k_eff))[:k_eff]
    idx = idx[np.argsort(-sims[idx])]

    titles = index.get("title", [])
    authors = index.get("author", [])
    previews = index.get("text_preview", [])
    interest_ages = index.get("interest_age", [])
    reading_ages = index.get("reading_age", [])

    hits: List[SimilarityHit] = []
    for i in idx:
        hits.append(
            SimilarityHit(
                idx=int(i),
                score=float(sims[i]),
                title=_safe_list_item(titles, i),
                author=_safe_list_item(authors, i),
                preview=_safe_list_item(previews, i),
                interest_age=_safe_list_item(interest_ages, i),
                reading_age=_safe_list_item(reading_ages, i),
            )
        )

    similarity_to_average = float(np.dot(q, avg_vec).item())
    return SimilarityResult(
        similarity_to_average=similarity_to_average,
        is_child_like=similarity_to_average >= threshold,
        top_k=hits,
        stats=index.get("stats", {}),
        model_name=model_name,
    )


def _safe_list_item(items: List[Any], idx: int) -> str:
    if not items:
        return ""
    if idx < 0 or idx >= len(items):
        return ""
    value = items[idx]
    return "" if value is None else str(value)


def json_load(path: Path) -> Dict[str, Any]:
    import json

    with path.open("r", encoding="utf-8") as f:
        return json.load(f)
