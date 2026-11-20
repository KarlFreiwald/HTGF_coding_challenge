"""Local, single-process interview store. Each operation uses a short transaction."""
import os
import sqlite3
from contextlib import closing, contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


def now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


@contextmanager
def database():
    path = Path(os.getenv("INTERVIEW_DB", "data/interviews.sqlite"))
    with closing(sqlite3.connect(path)) as db:
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
        with db:
            yield db


def initialize():
    Path(os.getenv("INTERVIEW_DB", "data/interviews.sqlite")).parent.mkdir(parents=True, exist_ok=True)
    with database() as db:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS conversations (
                id TEXT PRIMARY KEY NOT NULL, started_at TEXT NOT NULL, ended_at TEXT,
                status TEXT NOT NULL CHECK(status IN ('active','ended','interrupted')),
                language TEXT NOT NULL, tone TEXT NOT NULL, provider TEXT NOT NULL, model TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY NOT NULL, conversation_id TEXT NOT NULL REFERENCES conversations(id),
                position INTEGER NOT NULL, turn_id INTEGER NOT NULL, role TEXT NOT NULL CHECK(role IN ('user','assistant')),
                content TEXT NOT NULL, created_at TEXT NOT NULL,
                UNIQUE(conversation_id, position), UNIQUE(conversation_id, turn_id, role)
            );
            CREATE INDEX IF NOT EXISTS conversation_date ON conversations(started_at DESC);
        """)
        # A previous process cannot still own a WebSocket in our single-worker deployment.
        db.execute("UPDATE conversations SET status='interrupted' WHERE status='active'")


def start(language, tone, model, provider):
    conversation_id = str(uuid4())
    with database() as db:
        db.execute("INSERT INTO conversations VALUES (?, ?, NULL, 'active', ?, ?, ?, ?)",
                   (conversation_id, now(), language, tone, provider, model))
    return conversation_id


def finish(conversation_id, status):
    with database() as db:
        db.execute("UPDATE conversations SET status=?, ended_at=? WHERE id=? AND status='active'",
                   (status, now(), conversation_id))


def messages(db, conversation_id):
    return [dict(row) for row in db.execute(
        "SELECT role, content, turn_id FROM messages WHERE conversation_id=? ORDER BY position", (conversation_id,)
    )]


def append(conversation_id, turn_id, role, content):
    with database() as db:
        db.execute("BEGIN IMMEDIATE")
        conversation = db.execute("SELECT status FROM conversations WHERE id=?", (conversation_id,)).fetchone()
        if not conversation or conversation["status"] != "active":
            return False
        if role == "assistant":
            # Additional speech during generation supersedes the outdated question.
            last = db.execute("SELECT turn_id, role FROM messages WHERE conversation_id=? ORDER BY position DESC LIMIT 1",
                              (conversation_id,)).fetchone()
            if not last or tuple(last) != (turn_id, "user"):
                return False
        cursor = db.execute("""
            INSERT INTO messages(id, conversation_id, position, turn_id, role, content, created_at)
            SELECT ?, ?, COALESCE(MAX(position), 0)+1, ?, ?, ?, ? FROM messages WHERE conversation_id=?
            ON CONFLICT(conversation_id, turn_id, role) DO NOTHING
        """, (str(uuid4()), conversation_id, turn_id, role, content, now(), conversation_id))
        return cursor.rowcount == 1


def snapshot(conversation_id):
    with database() as db:
        db.execute("BEGIN")
        row = db.execute("SELECT * FROM conversations WHERE id=?", (conversation_id,)).fetchone()
        if row:
            return dict(row), messages(db, conversation_id)


def past_conversations():
    with database() as db:
        rows = db.execute("""
            SELECT id, started_at, status, language FROM conversations
            WHERE status IN ('ended', 'interrupted') ORDER BY started_at DESC, rowid DESC
        """)
        return [dict(row) for row in rows]
