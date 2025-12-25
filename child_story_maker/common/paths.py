from __future__ import annotations

from pathlib import Path


def repo_root() -> Path:
    # This file lives at: <repo>/child_story_maker/common/paths.py
    return Path(__file__).resolve().parents[2]

