# Copyright (c) 2026 Taras Bulubas. All rights reserved.
# Use requires prior written permission; see LICENSE.

"""SQLite cache: posts, transcripts, image notes and analyses.

Transcription and LLM calls take minutes; everything they produce is stored
so asking again about the same post is instant. Keys include the model name,
so switching models produces fresh results instead of stale ones.
"""

from __future__ import annotations

import json
import shutil
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

from twittermcp.core import config

DB_PATH = config.DATA_DIR / "twittermcp.db"
SCHEMA_VERSION = 1


def _v1(con: sqlite3.Connection) -> None:
    con.executescript("""
        CREATE TABLE posts (
            id TEXT PRIMARY KEY,
            author_handle TEXT NOT NULL,
            created_at TEXT,
            data TEXT NOT NULL,
            fetched_at TEXT NOT NULL
        );
        CREATE TABLE transcripts (
            post_id TEXT NOT NULL,
            video_index INTEGER NOT NULL,
            model TEXT NOT NULL,
            data TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (post_id, video_index, model)
        );
        CREATE TABLE image_notes (
            post_id TEXT NOT NULL,
            media_key TEXT NOT NULL,
            model TEXT NOT NULL,
            text TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (post_id, media_key, model)
        );
        CREATE TABLE analyses (
            id INTEGER PRIMARY KEY,
            post_id TEXT NOT NULL,
            question TEXT NOT NULL DEFAULT '',
            language TEXT NOT NULL,
            model TEXT NOT NULL,
            data TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE (post_id, question, language, model)
        );
    """)


# version -> step that brings the schema from version - 1 to version
MIGRATIONS = {1: _v1}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def connect():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    try:
        with con:
            yield con
    finally:
        con.close()


def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with connect() as con:
        version = con.execute("PRAGMA user_version").fetchone()[0]
    if version >= SCHEMA_VERSION:
        return
    if version > 0:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        shutil.copy2(DB_PATH, DB_PATH.with_name(f"{DB_PATH.stem}-backup-v{version}-{stamp}.db"))
    with connect() as con:
        for v in range(version + 1, SCHEMA_VERSION + 1):
            MIGRATIONS[v](con)
            con.execute(f"PRAGMA user_version = {v}")


def save_post(post: dict) -> None:
    with connect() as con:
        con.execute(
            "INSERT OR REPLACE INTO posts (id, author_handle, created_at, data, fetched_at) VALUES (?, ?, ?, ?, ?)",
            (post["id"], post["author_handle"], post["created_at"], json.dumps(post), _now()))


def get_post(post_id: str) -> dict | None:
    with connect() as con:
        row = con.execute("SELECT data FROM posts WHERE id = ?", (post_id,)).fetchone()
    return json.loads(row["data"]) if row else None


def save_transcript(post_id: str, video_index: int, model: str, data: dict) -> None:
    with connect() as con:
        con.execute("INSERT OR REPLACE INTO transcripts VALUES (?, ?, ?, ?, ?)",
                    (post_id, video_index, model, json.dumps(data), _now()))


def get_transcript(post_id: str, video_index: int, model: str) -> dict | None:
    with connect() as con:
        row = con.execute(
            "SELECT data FROM transcripts WHERE post_id = ? AND video_index = ? AND model = ?",
            (post_id, video_index, model)).fetchone()
    return json.loads(row["data"]) if row else None


def save_image_note(post_id: str, media_key: str, model: str, text: str) -> None:
    with connect() as con:
        con.execute("INSERT OR REPLACE INTO image_notes VALUES (?, ?, ?, ?, ?)",
                    (post_id, media_key, model, text, _now()))


def get_image_note(post_id: str, media_key: str, model: str) -> str | None:
    with connect() as con:
        row = con.execute(
            "SELECT text FROM image_notes WHERE post_id = ? AND media_key = ? AND model = ?",
            (post_id, media_key, model)).fetchone()
    return row["text"] if row else None


def save_analysis(post_id: str, question: str, language: str, model: str, data: dict) -> None:
    with connect() as con:
        con.execute(
            "INSERT OR REPLACE INTO analyses (post_id, question, language, model, data, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (post_id, question, language, model, json.dumps(data), _now()))


def get_analysis(post_id: str, question: str, language: str, model: str) -> dict | None:
    with connect() as con:
        row = con.execute(
            "SELECT data FROM analyses WHERE post_id = ? AND question = ? AND language = ? AND model = ?",
            (post_id, question, language, model)).fetchone()
    return json.loads(row["data"]) if row else None


def recent_analyses(limit: int = 20) -> list[dict]:
    with connect() as con:
        rows = con.execute(
            "SELECT a.post_id, p.author_handle, a.question, a.language, a.model, a.created_at, "
            "json_extract(a.data, '$.summary') AS summary "
            "FROM analyses a JOIN posts p ON p.id = a.post_id ORDER BY a.id DESC LIMIT ?",
            (limit,)).fetchall()
    return [dict(r) for r in rows]
