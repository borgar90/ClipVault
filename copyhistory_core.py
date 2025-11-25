import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional

# Load environment variables from .env.local or .env if present
try:
    from dotenv import load_dotenv

    for env_name in (".env.local", ".env"):
        env_path = Path(__file__).with_name(env_name)
        if env_path.exists():
            load_dotenv(env_path, override=False)
except ImportError:
    # If python-dotenv is not installed, we simply skip file-based env loading.
    pass


DB_FILE = str(Path(__file__).with_name("history.db"))


@dataclass
class ClipItem:
    id: int
    created_at: str
    title: Optional[str]
    category: Optional[str]
    content: str


def get_db_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS clipboard_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            content TEXT NOT NULL,
            title TEXT,
            category TEXT
        )
        """
    )
    return conn


def add_clip(content: str) -> int:
    conn = get_db_connection()
    try:
        created_at = datetime.utcnow().isoformat(timespec="seconds") + "Z"
        cursor = conn.execute(
            "INSERT INTO clipboard_history (created_at, content) VALUES (?, ?)",
            (created_at, content),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def fetch_clips(limit: int = 20, search: Optional[str] = None) -> List[ClipItem]:
    conn = get_db_connection()
    try:
        if search:
            rows = conn.execute(
                """
                SELECT id, created_at, title, category, content
                FROM clipboard_history
                WHERE content LIKE ? OR title LIKE ? OR category LIKE ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (f"%{search}%", f"%{search}%", f"%{search}%", limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT id, created_at, title, category, content
                FROM clipboard_history
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

        return [
            ClipItem(
                id=row[0],
                created_at=row[1],
                title=row[2],
                category=row[3],
                content=row[4],
            )
            for row in rows
        ]
    finally:
        conn.close()


def get_clip_by_id(item_id: int) -> Optional[ClipItem]:
    conn = get_db_connection()
    try:
        row = conn.execute(
            """
            SELECT id, created_at, title, category, content
            FROM clipboard_history
            WHERE id = ?
            """,
            (item_id,),
        ).fetchone()
        if not row:
            return None
        return ClipItem(
            id=row[0],
            created_at=row[1],
            title=row[2],
            category=row[3],
            content=row[4],
        )
    finally:
        conn.close()


def get_all_clips() -> List[ClipItem]:
    """Return all clips in the database, newest first."""
    conn = get_db_connection()
    try:
        rows = conn.execute(
            """
            SELECT id, created_at, title, category, content
            FROM clipboard_history
            ORDER BY id DESC
            """
        ).fetchall()
        return [
            ClipItem(
                id=row[0],
                created_at=row[1],
                title=row[2],
                category=row[3],
                content=row[4],
            )
            for row in rows
        ]
    finally:
        conn.close()


def delete_all_clips() -> int:
    """Delete all clips from the database. Returns number of rows deleted."""
    conn = get_db_connection()
    try:
        cursor = conn.execute("DELETE FROM clipboard_history")
        conn.commit()
        return cursor.rowcount
    finally:
        conn.close()

