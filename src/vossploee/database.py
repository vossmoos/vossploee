from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

import aiosqlite


SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    parent_id TEXT REFERENCES tasks(id) ON DELETE CASCADE,
    root_id TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    queue_name TEXT NOT NULL,
    task_kind TEXT NOT NULL,
    status TEXT NOT NULL,
    agent_name TEXT NOT NULL,
    capability_name TEXT NOT NULL DEFAULT 'consultant',
    gherkin TEXT,
    result TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    claimed_at TEXT,
    completed_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_tasks_parent_id ON tasks(parent_id);
CREATE INDEX IF NOT EXISTS idx_tasks_root_id ON tasks(root_id);
CREATE INDEX IF NOT EXISTS idx_tasks_queue_status_created ON tasks(queue_name, status, created_at);
"""


class Database:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

    async def initialize(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        async with self.connection() as conn:
            await conn.executescript(SCHEMA)
            await self._migrate(conn)
            await conn.commit()

    @asynccontextmanager
    async def connection(self) -> AsyncIterator[aiosqlite.Connection]:
        conn = await aiosqlite.connect(self.database_path)
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys = ON;")
        try:
            yield conn
        finally:
            await conn.close()

    @staticmethod
    async def _migrate(conn: aiosqlite.Connection) -> None:
        cursor = await conn.execute("PRAGMA table_info(tasks)")
        columns = {row["name"] for row in await cursor.fetchall()}

        if "capability_name" not in columns:
            await conn.execute(
                "ALTER TABLE tasks ADD COLUMN capability_name TEXT NOT NULL DEFAULT 'consultant'"
            )
