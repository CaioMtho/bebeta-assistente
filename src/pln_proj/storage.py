from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import datetime
from pathlib import Path
import sqlite3
import unicodedata
from typing import Iterator


def _utc_now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()


def _normalize_search(text: str) -> str:
    no_accents = "".join(
        char
        for char in unicodedata.normalize("NFKD", text.lower())
        if not unicodedata.combining(char)
    )
    return " ".join(no_accents.split())


@dataclass(frozen=True)
class Note:
    """Persisted note or reminder stored in SQLite."""

    id: int
    content: str
    completed: bool
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class ChatMessageRecord:
    """Chat message record stored in SQLite."""

    id: int
    role: str
    content: str
    intent: str | None
    confidence: float | None
    created_at: str


class Database:
    """Manage SQLite connections, schema initialization, and one-time legacy migration."""

    def __init__(self, db_path: Path | str) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.db_path, check_same_thread=False)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _init_schema(self) -> None:
        with self.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS notes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    content TEXT NOT NULL,
                    completed INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS chat_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    intent TEXT,
                    confidence REAL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                """
            )

    def migrate_legacy_txt(self, legacy_path: Path | str) -> int:
        """Import lines from a legacy text file once per database."""
        path = Path(legacy_path)
        with self.connect() as connection:
            row = connection.execute(
                "SELECT value FROM metadata WHERE key = 'legacy_txt_migrated'"
            ).fetchone()
            if row is not None:
                return 0

            imported = 0
            if path.exists():
                now = _utc_now_iso()
                lines = [
                    line.strip()
                    for line in path.read_text(encoding="utf-8").splitlines()
                    if line.strip()
                ]
                for line in lines:
                    connection.execute(
                        """
                        INSERT INTO notes (content, completed, created_at, updated_at)
                        VALUES (?, 0, ?, ?)
                        """,
                        (line, now, now),
                    )
                    imported += 1

            connection.execute(
                "INSERT INTO metadata (key, value) VALUES ('legacy_txt_migrated', '1')"
            )
            return imported


class NoteRepository:
    """CRUD operations for the `notes` table."""

    def __init__(self, database: Database) -> None:
        self.database = database

    @staticmethod
    def _row_to_note(row: sqlite3.Row) -> Note:
        return Note(
            id=int(row["id"]),
            content=str(row["content"]),
            completed=bool(row["completed"]),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )

    def create(self, content: str) -> Note:
        cleaned = content.strip()
        if not cleaned:
            raise ValueError("Note content cannot be empty.")
        now = _utc_now_iso()
        with self.database.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO notes (content, completed, created_at, updated_at)
                VALUES (?, 0, ?, ?)
                """,
                (cleaned, now, now),
            )
            note_id = int(cursor.lastrowid)
            row = connection.execute(
                "SELECT * FROM notes WHERE id = ?", (note_id,)
            ).fetchone()
            assert row is not None
            return self._row_to_note(row)

    def get_by_id(self, note_id: int) -> Note | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM notes WHERE id = ?", (note_id,)
            ).fetchone()
            return self._row_to_note(row) if row is not None else None

    def list_all(
        self,
        *,
        include_completed: bool = True,
        search: str | None = None,
    ) -> list[Note]:
        query_sql = "SELECT * FROM notes"
        if not include_completed:
            query_sql += " WHERE completed = 0"
        query_sql += " ORDER BY completed ASC, id ASC"

        with self.database.connect() as connection:
            rows = connection.execute(query_sql).fetchall()
        notes = [self._row_to_note(row) for row in rows]

        if search:
            needle = _normalize_search(search)
            notes = [
                note for note in notes if needle in _normalize_search(note.content)
            ]
        return notes

    def find_matches(self, query: str) -> list[Note]:
        """Find notes matching the normalized substring or keyword tokens."""
        all_notes = self.list_all()
        needle = _normalize_search(query)
        if not needle:
            return []

        exact_matches = [
            note for note in all_notes if needle in _normalize_search(note.content)
        ]
        if exact_matches:
            return exact_matches

        tokens = [token for token in needle.split() if len(token) > 2]
        if not tokens:
            return []

        scored: list[tuple[int, Note]] = []
        for note in all_notes:
            normalized_content = _normalize_search(note.content)
            hits = sum(1 for token in tokens if token in normalized_content)
            if hits > 0:
                scored.append((hits, note))
        scored.sort(key=lambda item: (-item[0], item[1].id))
        return [item[1] for item in scored]

    def update(
        self,
        note_id: int,
        *,
        content: str | None = None,
        completed: bool | None = None,
    ) -> Note | None:
        existing = self.get_by_id(note_id)
        if existing is None:
            return None

        new_content = existing.content if content is None else content.strip()
        if not new_content:
            raise ValueError("Note content cannot be empty.")
        new_completed = existing.completed if completed is None else bool(completed)
        now = _utc_now_iso()

        with self.database.connect() as connection:
            connection.execute(
                """
                UPDATE notes
                SET content = ?, completed = ?, updated_at = ?
                WHERE id = ?
                """,
                (new_content, int(new_completed), now, note_id),
            )
            row = connection.execute(
                "SELECT * FROM notes WHERE id = ?", (note_id,)
            ).fetchone()
            return self._row_to_note(row) if row is not None else None

    def delete(self, note_id: int) -> bool:
        with self.database.connect() as connection:
            cursor = connection.execute("DELETE FROM notes WHERE id = ?", (note_id,))
            return cursor.rowcount > 0

    def clear_all(self) -> int:
        with self.database.connect() as connection:
            cursor = connection.execute("DELETE FROM notes")
            return int(cursor.rowcount)


class ChatHistoryRepository:
    """Optional persistence for chat message history."""

    def __init__(self, database: Database) -> None:
        self.database = database

    def add(
        self,
        role: str,
        content: str,
        *,
        intent: str | None = None,
        confidence: float | None = None,
    ) -> ChatMessageRecord:
        now = _utc_now_iso()
        with self.database.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO chat_history (role, content, intent, confidence, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (role, content, intent, confidence, now),
            )
            message_id = int(cursor.lastrowid)
            row = connection.execute(
                "SELECT * FROM chat_history WHERE id = ?", (message_id,)
            ).fetchone()
            assert row is not None
            return ChatMessageRecord(
                id=int(row["id"]),
                role=str(row["role"]),
                content=str(row["content"]),
                intent=row["intent"],
                confidence=float(row["confidence"]) if row["confidence"] is not None else None,
                created_at=str(row["created_at"]),
            )

    def recent(self, limit: int = 50) -> list[ChatMessageRecord]:
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM chat_history ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        rows.reverse()
        return [
            ChatMessageRecord(
                id=int(row["id"]),
                role=str(row["role"]),
                content=str(row["content"]),
                intent=row["intent"],
                confidence=float(row["confidence"]) if row["confidence"] is not None else None,
                created_at=str(row["created_at"]),
            )
            for row in rows
        ]

    def clear(self) -> int:
        with self.database.connect() as connection:
            cursor = connection.execute("DELETE FROM chat_history")
            return int(cursor.rowcount)
