from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional


class ConversationStore:
    """SQLite-backed short-term memory for chat sessions."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self) -> None:
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                user_id TEXT,
                title TEXT,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL
            )
            """
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                metadata TEXT,
                created_at INTEGER NOT NULL
            )
            """
        )
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_messages_session_id ON messages(session_id, created_at)")
        self.conn.commit()

    def ensure_session(self, session_id: str, user_id: Optional[str] = None, title: Optional[str] = None) -> None:
        now = int(time.time())
        existing = self.conn.execute("SELECT session_id FROM sessions WHERE session_id = ?", (session_id,)).fetchone()
        if existing is None:
            self.conn.execute(
                """
                INSERT INTO sessions(session_id, user_id, title, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (session_id, user_id, title or session_id, now, now),
            )
        else:
            self.conn.execute(
                "UPDATE sessions SET updated_at = ?, user_id = COALESCE(?, user_id) WHERE session_id = ?",
                (now, user_id, session_id),
            )
        self.conn.commit()

    def append_message(
        self,
        session_id: str,
        role: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
        user_id: Optional[str] = None,
    ) -> None:
        self.ensure_session(session_id=session_id, user_id=user_id)
        now = int(time.time())
        self.conn.execute(
            """
            INSERT INTO messages(session_id, role, content, metadata, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                session_id,
                role,
                content,
                json.dumps(metadata or {}, ensure_ascii=False),
                now,
            ),
        )
        self.conn.execute("UPDATE sessions SET updated_at = ? WHERE session_id = ?", (now, session_id))
        self.conn.commit()

    def load_recent_messages(self, session_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT role, content, metadata, created_at
            FROM messages
            WHERE session_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (session_id, limit),
        ).fetchall()
        messages = []
        for row in reversed(rows):
            messages.append(
                {
                    "role": str(row["role"]),
                    "content": str(row["content"]),
                    "metadata": json.loads(row["metadata"] or "{}"),
                    "created_at": int(row["created_at"]),
                }
            )
        return messages

    def load_all_messages(self, session_id: str) -> List[Dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT role, content, metadata, created_at
            FROM messages
            WHERE session_id = ?
            ORDER BY id ASC
            """,
            (session_id,),
        ).fetchall()
        return [
            {
                "role": str(row["role"]),
                "content": str(row["content"]),
                "metadata": json.loads(row["metadata"] or "{}"),
                "created_at": int(row["created_at"]),
            }
            for row in rows
        ]

    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        row = self.conn.execute("SELECT * FROM sessions WHERE session_id = ?", (session_id,)).fetchone()
        return None if row is None else dict(row)

    def list_sessions(self, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        if user_id:
            rows = self.conn.execute(
                "SELECT * FROM sessions WHERE user_id = ? ORDER BY updated_at DESC",
                (user_id,),
            ).fetchall()
        else:
            rows = self.conn.execute("SELECT * FROM sessions ORDER BY updated_at DESC").fetchall()
        return [dict(row) for row in rows]

    def delete_session(self, session_id: str) -> bool:
        self.conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
        cursor = self.conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
        self.conn.commit()
        return cursor.rowcount > 0

    def close(self) -> None:
        self.conn.close()
