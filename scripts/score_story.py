import argparse
import json
from pathlib import Path

from child_story_maker.ml.similarity import compare_text


def _load_story_text(path: Path) -> str:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    sections = data.get("sections") or data.get("chapters") or []
    parts = []
    for sec in sections:
        title = (sec.get("title") or "").strip()
        text = (sec.get("text") or "").strip()
        if title:
            parts.append(title)
        if text:
            parts.append(text)
    return "\n\n".join(parts)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compare a story to children_books embeddings."
    )
    parser.add_argument("--story-json", type=str, help="Path to story.json")
    parser.add_argument("--text", type=str, help="Raw story text")
    parser.add_argument("--k", type=int, default=3, help="Top-k matches")
    args = parser.parse_args()

    if not args.story_json and not args.text:
        parser.error("Provide --story-json or --text.")

    if args.story_json:
        text = _load_story_text(Path(args.story_json))
    else:
        text = args.text

    result = compare_text(text, k=args.k)
    print(f"Similarity to corpus average: {result.similarity_to_average:.3f}")
    print("Top matches:")
    for hit in result.top_k:
        meta = " | ".join(
            p
            for p in [
                hit.author,
                f"interest age: {hit.interest_age}" if hit.interest_age else "",
                f"reading age: {hit.reading_age}" if hit.reading_age else "",
            ]
            if p
        )
        print(f"- {hit.title} (score {hit.score:.3f})")
        if meta:
            print(f"  {meta}")
        if hit.preview:
            print(f"  {hit.preview}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
