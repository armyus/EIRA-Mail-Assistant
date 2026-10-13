"""Small local SQLite store for duplicate prevention and watch checkpoints."""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path


class ProcessStore:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        with self._connect() as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS processed ("
                "message_id TEXT PRIMARY KEY, state TEXT NOT NULL, detail TEXT NOT NULL DEFAULT '', updated_at INTEGER NOT NULL)"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
            )

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path, timeout=10)

    def claim(self, message_id: str) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                "INSERT OR IGNORE INTO processed(message_id, state, updated_at) VALUES (?, 'processing', ?)",
                (message_id, int(time.time())),
            )
            return cursor.rowcount == 1

    def contains(self, message_id: str) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT 1 FROM processed WHERE message_id = ?", (message_id,)
            ).fetchone()
        return row is not None

    def finish(self, message_id: str, state: str, detail: str = "") -> None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE processed SET state = ?, detail = ?, updated_at = ? WHERE message_id = ?",
                (state, detail[:1000], int(time.time()), message_id),
            )

    def checkpoint(self) -> int | None:
        with self._connect() as connection:
            row = connection.execute("SELECT value FROM settings WHERE key = 'watch_checkpoint'").fetchone()
        return int(row[0]) if row else None

    def set_checkpoint(self, value: int) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO settings(key, value) VALUES ('watch_checkpoint', ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (str(value),),
            )
