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
    capability_name TEXT NOT NULL DEFAULT 'core',
    gherkin TEXT,
    result TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    claimed_at TEXT,
    completed_at TEXT,
    scheduled_at TEXT,
    queue_policy TEXT NOT NULL DEFAULT 'fifo' CHECK (queue_policy IN ('fifo', 'lifo'))
);

CREATE INDEX IF NOT EXISTS idx_tasks_parent_id ON tasks(parent_id);
CREATE INDEX IF NOT EXISTS idx_tasks_root_id ON tasks(root_id);
CREATE INDEX IF NOT EXISTS idx_tasks_queue_status_created ON tasks(queue_name, status, created_at);

CREATE TABLE IF NOT EXISTS tasklog (
    id TEXT PRIMARY KEY,
    root_id TEXT NOT NULL,
    capability_name TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_tasklog_root_id ON tasklog(root_id);
CREATE INDEX IF NOT EXISTS idx_tasklog_capability ON tasklog(capability_name);

CREATE TABLE IF NOT EXISTS upwork_processed_jobs (
    job_id TEXT PRIMARY KEY NOT NULL,
    processed_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_upwork_processed_at ON upwork_processed_jobs(processed_at);

-- Singleton row (id=1) holding the latest Upwork OAuth2 tokens. Upwork rotates the
-- refresh_token on every /oauth2/token call, so we must persist the rotated value back
-- or the next refresh fails with `invalid_grant` and forces a new browser flow.
CREATE TABLE IF NOT EXISTS upwork_oauth_tokens (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    access_token TEXT NOT NULL,
    refresh_token TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS newsroom_processed_articles (
    article_url TEXT PRIMARY KEY NOT NULL,
    processed_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_newsroom_processed_at ON newsroom_processed_articles(processed_at);
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
                "ALTER TABLE tasks ADD COLUMN capability_name TEXT NOT NULL DEFAULT 'core'"
            )

        cursor = await conn.execute("PRAGMA table_info(tasks)")
        columns = {row["name"] for row in await cursor.fetchall()}
        if "scheduled_at" not in columns:
            await conn.execute("ALTER TABLE tasks ADD COLUMN scheduled_at TEXT")

        cursor = await conn.execute("PRAGMA table_info(tasks)")
        columns = {row["name"] for row in await cursor.fetchall()}
        if "queue_policy" not in columns:
            await conn.execute(
                "ALTER TABLE tasks ADD COLUMN queue_policy TEXT NOT NULL DEFAULT 'fifo'"
            )

        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_tasks_scheduled ON tasks(scheduled_at)"
        )

        cursor = await conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='tasklog'"
        )
        if await cursor.fetchone() is None:
            await conn.executescript(
                """
                CREATE TABLE tasklog (
                    id TEXT PRIMARY KEY,
                    root_id TEXT NOT NULL,
                    capability_name TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_tasklog_root_id ON tasklog(root_id);
                CREATE INDEX IF NOT EXISTS idx_tasklog_capability ON tasklog(capability_name);
                """
            )

        cursor = await conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='upwork_processed_jobs'"
        )
        if await cursor.fetchone() is None:
            await conn.executescript(
                """
                CREATE TABLE upwork_processed_jobs (
                    job_id TEXT PRIMARY KEY NOT NULL,
                    processed_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_upwork_processed_at ON upwork_processed_jobs(processed_at);
                """
            )

        cursor = await conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='upwork_oauth_tokens'"
        )
        if await cursor.fetchone() is None:
            await conn.executescript(
                """
                CREATE TABLE upwork_oauth_tokens (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    access_token TEXT NOT NULL,
                    refresh_token TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )

        cursor = await conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='newsroom_processed_articles'"
        )
        if await cursor.fetchone() is None:
            await conn.executescript(
                """
                CREATE TABLE newsroom_processed_articles (
                    article_url TEXT PRIMARY KEY NOT NULL,
                    processed_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_newsroom_processed_at ON newsroom_processed_articles(processed_at);
                """
            )
