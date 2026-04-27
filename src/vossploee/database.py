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
    role_id TEXT NOT NULL,
    capability_id TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    payload_json TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL,
    queue_policy TEXT NOT NULL DEFAULT 'fifo' CHECK (queue_policy IN ('fifo', 'lifo')),
    scheduled_at TEXT,
    refining_user_json TEXT,
    result TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    claimed_at TEXT,
    completed_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_tasks_status_scheduled ON tasks(status, scheduled_at);
CREATE INDEX IF NOT EXISTS idx_tasks_role_status_created ON tasks(role_id, status, created_at);
CREATE INDEX IF NOT EXISTS idx_tasks_root_id ON tasks(root_id);

CREATE TABLE IF NOT EXISTS tasklog (
    id TEXT PRIMARY KEY,
    root_id TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_tasklog_root_id ON tasklog(root_id);

CREATE TABLE IF NOT EXISTS channel_messages (
    id TEXT PRIMARY KEY,
    channel_id TEXT NOT NULL,
    sender_json TEXT NOT NULL,
    receiver_json TEXT NOT NULL,
    body_json TEXT NOT NULL,
    in_reply_to TEXT,
    task_id TEXT,
    dedupe_key TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_channel_messages_lookup ON channel_messages(channel_id, receiver_json, created_at);
CREATE UNIQUE INDEX IF NOT EXISTS idx_channel_messages_dedupe ON channel_messages(channel_id, dedupe_key);

CREATE TABLE IF NOT EXISTS reasoning (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    role_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    model TEXT NOT NULL,
    confidence REAL NOT NULL,
    explanation TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_reasoning_role_created ON reasoning(role_id, created_at);
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
        # Kept intentionally lightweight: existing DBs may still carry old columns.
        # New runtime only reads/writes fields defined in the v0.1.0 schema.
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_status_scheduled ON tasks(status, scheduled_at)")
