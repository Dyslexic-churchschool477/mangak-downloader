"""
SQLite download history database.

Stores a record of every completed download in ``history.db``
located in the project root directory.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from mangak.core.exceptions import MangaKError

# ──────────────────────────────────────────────
#  Schema
# ──────────────────────────────────────────────

_SCHEMA = """
CREATE TABLE IF NOT EXISTS downloads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    manga_slug TEXT NOT NULL,
    manga_name TEXT NOT NULL,
    chapter_slug TEXT NOT NULL,
    chapter_name TEXT NOT NULL,
    format TEXT NOT NULL,
    pages_count INTEGER,
    file_path TEXT,
    file_size_kb INTEGER,
    downloaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_manga ON downloads(manga_slug);
CREATE INDEX IF NOT EXISTS idx_date ON downloads(downloaded_at);
"""

_ROW_FIELDS = [
    "id",
    "manga_slug",
    "manga_name",
    "chapter_slug",
    "chapter_name",
    "format",
    "pages_count",
    "file_path",
    "file_size_kb",
    "downloaded_at",
]


def _project_root() -> Path:
    """Return the project root directory (grandparent of ``src/mangak/core/``)."""
    return Path(__file__).resolve().parents[3]


# ──────────────────────────────────────────────
#  History record type
# ──────────────────────────────────────────────


class DownloadRecord(dict):
    """
    A single download history record.

    Behaves like a dict with attribute-style access for convenience.
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(kwargs)
        self.__dict__ = self

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> DownloadRecord:
        """Create a record from an ``sqlite3.Row``."""
        return cls(**dict(zip(_ROW_FIELDS, row)))


# ──────────────────────────────────────────────
#  Database manager
# ──────────────────────────────────────────────


class DownloadDB:
    """
    SQLite-backed download history.

    Manages the ``history.db`` file in the project root.

    Usage::

        db = DownloadDB()
        db.record_download("nano-machine", "Nano Machine", "chapter-1", ...)
        records = db.get_history(limit=20)
        db.clear_history()
    """

    def __init__(self, db_path: Optional[Path] = None) -> None:
        self._path: Path = db_path or (_project_root() / "history.db")
        self._conn: Optional[sqlite3.Connection] = None
        self._init_db()

    # ── Connection management ───────────────────

    def _connect(self) -> sqlite3.Connection:
        """Open (or return) the connection, creating the DB file if needed."""
        if self._conn is None:
            self._conn = sqlite3.connect(str(self._path))
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
        return self._conn

    def close(self) -> None:
        """Close the database connection."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def __enter__(self) -> DownloadDB:
        self._connect()
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    # ── Schema initialisation ──────────────────

    def _init_db(self) -> None:
        """Ensure the database file and schema exist."""
        conn = self._connect()
        conn.executescript(_SCHEMA)
        conn.commit()

    # ── CRUD operations ─────────────────────────

    def record_download(
        self,
        manga_slug: str,
        manga_name: str,
        chapter_slug: str,
        chapter_name: str,
        format: str,
        pages_count: Optional[int] = None,
        file_path: Optional[str] = None,
        file_size_kb: Optional[int] = None,
    ) -> int:
        """
        Insert a new download record and return its ``id``.

        ``downloaded_at`` is automatically set to the current timestamp.
        """
        conn = self._connect()
        try:
            cursor = conn.execute(
                """
                INSERT INTO downloads
                    (manga_slug, manga_name, chapter_slug, chapter_name,
                     format, pages_count, file_path, file_size_kb)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    manga_slug,
                    manga_name,
                    chapter_slug,
                    chapter_name,
                    format,
                    pages_count,
                    file_path,
                    file_size_kb,
                ),
            )
            conn.commit()
            return cursor.lastrowid  # type: ignore[return-value]
        except sqlite3.Error as exc:
            raise MangaKError(f"Failed to record download: {exc}") from exc

    def get_history(
        self,
        limit: int = 50,
        offset: int = 0,
    ) -> list[DownloadRecord]:
        """
        Return download history records ordered by most recent first.

        *limit* defaults to 50, *offset* defaults to 0.
        """
        conn = self._connect()
        try:
            rows = conn.execute(
                """
                SELECT * FROM downloads
                ORDER BY downloaded_at DESC
                LIMIT ? OFFSET ?
                """,
                (limit, offset),
            ).fetchall()
            return [DownloadRecord.from_row(r) for r in rows]
        except sqlite3.Error as exc:
            raise MangaKError(
                f"Failed to query download history: {exc}"
            ) from exc

    def search_history(
        self,
        query: str,
        limit: int = 50,
        offset: int = 0,
    ) -> list[DownloadRecord]:
        """
        Search download history by manga slug, manga name, or chapter name.

        Uses a ``LIKE`` search against the three text columns.
        """
        conn = self._connect()
        like = f"%{query}%"
        try:
            rows = conn.execute(
                """
                SELECT * FROM downloads
                WHERE manga_slug LIKE ?
                   OR manga_name LIKE ?
                   OR chapter_name LIKE ?
                ORDER BY downloaded_at DESC
                LIMIT ? OFFSET ?
                """,
                (like, like, like, limit, offset),
            ).fetchall()
            return [DownloadRecord.from_row(r) for r in rows]
        except sqlite3.Error as exc:
            raise MangaKError(
                f"Failed to search download history: {exc}"
            ) from exc

    def get_stats(self) -> dict[str, Any]:
        """
        Return summary statistics about the download history.

        Returns a dict with:
          - ``total_downloads``
          - ``unique_manga``
          - ``total_formats``
          - ``latest_download`` (datetime string or None)
        """
        conn = self._connect()
        try:
            total = conn.execute(
                "SELECT COUNT(*) FROM downloads"
            ).fetchone()[0]
            unique = conn.execute(
                "SELECT COUNT(DISTINCT manga_slug) FROM downloads"
            ).fetchone()[0]
            formats = conn.execute(
                "SELECT COUNT(DISTINCT format) FROM downloads"
            ).fetchone()[0]
            latest = conn.execute(
                "SELECT downloaded_at FROM downloads ORDER BY downloaded_at DESC LIMIT 1"
            ).fetchone()
            return {
                "total_downloads": total,
                "unique_manga": unique,
                "total_formats": formats,
                "latest_download": latest[0] if latest else None,
            }
        except sqlite3.Error as exc:
            raise MangaKError(
                f"Failed to get download stats: {exc}"
            ) from exc

    def clear_history(self) -> int:
        """
        Delete **all** download history records.

        Returns the number of rows deleted.
        """
        conn = self._connect()
        try:
            cursor = conn.execute("DELETE FROM downloads")
            conn.commit()
            return cursor.rowcount
        except sqlite3.Error as exc:
            raise MangaKError(
                f"Failed to clear download history: {exc}"
            ) from exc

    def delete_record(self, record_id: int) -> bool:
        """
        Delete a single download record by its ``id``.

        Returns ``True`` if a row was deleted, ``False`` otherwise.
        """
        conn = self._connect()
        try:
            cursor = conn.execute(
                "DELETE FROM downloads WHERE id = ?", (record_id,)
            )
            conn.commit()
            return cursor.rowcount > 0
        except sqlite3.Error as exc:
            raise MangaKError(
                f"Failed to delete record {record_id}: {exc}"
            ) from exc
