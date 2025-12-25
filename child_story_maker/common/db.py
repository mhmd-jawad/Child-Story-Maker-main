from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime
from typing import List, Optional

from child_story_maker.common.auth import hash_password, verify_password
from child_story_maker.common.paths import repo_root

DB_PATH = repo_root() / "data" / "app.db"


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


def init_db() -> None:
    with _connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS parents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS children (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                parent_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                age INTEGER NOT NULL,
                interests TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(parent_id) REFERENCES parents(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                parent_id INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(parent_id) REFERENCES parents(id) ON DELETE CASCADE
            );
            """
        )


def create_parent(email: str, password: str) -> int:
    email = (email or "").strip().lower()
    if not email or "@" not in email:
        raise ValueError("Please enter a valid email.")
    pw_hash = hash_password(password)
    now = datetime.utcnow().isoformat()
    with _connect() as conn:
        try:
            cur = conn.execute(
                "INSERT INTO parents (email, password_hash, created_at) VALUES (?, ?, ?)",
                (email, pw_hash, now),
            )
            return int(cur.lastrowid)
        except sqlite3.IntegrityError as exc:
            raise ValueError("Email already registered.") from exc


def authenticate_parent(email: str, password: str) -> Optional[int]:
    email = (email or "").strip().lower()
    if not email or not password:
        return None
    with _connect() as conn:
        row = conn.execute(
            "SELECT id, password_hash FROM parents WHERE email = ?",
            (email,),
        ).fetchone()
    if not row:
        return None
    if verify_password(password, row["password_hash"]):
        return int(row["id"])
    return None


def get_parent(parent_id: int) -> Optional[sqlite3.Row]:
    with _connect() as conn:
        row = conn.execute(
            "SELECT id, email FROM parents WHERE id = ?",
            (parent_id,),
        ).fetchone()
    return row


def create_session(parent_id: int) -> str:
    token = uuid.uuid4().hex
    now = datetime.utcnow().isoformat()
    with _connect() as conn:
        conn.execute(
            "INSERT INTO sessions (token, parent_id, created_at) VALUES (?, ?, ?)",
            (token, parent_id, now),
        )
    return token


def get_parent_id_for_token(token: str) -> Optional[int]:
    if not token:
        return None
    with _connect() as conn:
        row = conn.execute(
            "SELECT parent_id FROM sessions WHERE token = ?",
            (token,),
        ).fetchone()
    if not row:
        return None
    return int(row["parent_id"])


def delete_session(token: str) -> None:
    if not token:
        return
    with _connect() as conn:
        conn.execute("DELETE FROM sessions WHERE token = ?", (token,))


def list_children(parent_id: int) -> List[sqlite3.Row]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT id, name, age, interests FROM children WHERE parent_id = ? ORDER BY id",
            (parent_id,),
        ).fetchall()
    return list(rows)


def get_child(parent_id: int, child_id: int) -> Optional[sqlite3.Row]:
    with _connect() as conn:
        row = conn.execute(
            "SELECT id, name, age, interests FROM children WHERE parent_id = ? AND id = ?",
            (parent_id, child_id),
        ).fetchone()
    return row


def create_child(parent_id: int, name: str, age: int, interests: str) -> int:
    name = (name or "").strip()
    if not name:
        raise ValueError("Child name is required.")
    if age < 2 or age > 12:
        raise ValueError("Age must be between 2 and 12.")
    interests = (interests or "").strip()
    if not interests:
        raise ValueError("Interests are required.")
    now = datetime.utcnow().isoformat()
    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO children (parent_id, name, age, interests, created_at) VALUES (?, ?, ?, ?, ?)",
            (parent_id, name, age, interests, now),
        )
        return int(cur.lastrowid)


def delete_child(parent_id: int, child_id: int) -> None:
    with _connect() as conn:
        conn.execute(
            "DELETE FROM children WHERE parent_id = ? AND id = ?",
            (parent_id, child_id),
        )
