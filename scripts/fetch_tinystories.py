import argparse
import csv
from pathlib import Path
import urllib.request


DATASET_URL = (
    "https://huggingface.co/datasets/roneneldan/TinyStories/resolve/main/"
    "TinyStories-valid.txt"
)


def download(url: str, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url, timeout=120) as resp:
        out_path.write_bytes(resp.read())


def parse_stories(text_path: Path):
    text = text_path.read_text(encoding="utf-8", errors="replace")
    for part in text.split("<|endoftext|>"):
        story = part.strip()
        if story:
            yield story


def build_csv(stories, out_csv: Path, limit: int | None) -> int:
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with out_csv.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Title", "Author", "Desc", "Inerest_age", "Reading_age"])
        for i, story in enumerate(stories, start=1):
            if limit and i > limit:
                break
            title = f"TinyStory {i}"
            writer.writerow([title, "TinyStories", story, "", ""])
            count += 1
    return count


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Download TinyStories validation split and convert to CSV."
    )
    parser.add_argument(
        "--out-csv",
        default="data/children_books.csv",
        help="Output CSV path",
    )
    parser.add_argument(
        "--out-raw",
        default="data/tinystories_valid.txt",
        help="Raw text download path",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional max number of stories to write",
    )
    args = parser.parse_args()

    raw_path = Path(args.out_raw)
    if not raw_path.exists():
        print(f"Downloading {DATASET_URL} -> {raw_path}")
        download(DATASET_URL, raw_path)
    else:
        print(f"Using existing {raw_path}")

    stories = parse_stories(raw_path)
    out_csv = Path(args.out_csv)
    count = build_csv(stories, out_csv, args.limit)
    print(f"Wrote {count} stories to {out_csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
