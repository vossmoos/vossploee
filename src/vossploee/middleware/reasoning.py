from __future__ import annotations

import logging

from vossploee.database import Database

logger = logging.getLogger(__name__)


class ReasoningRecorder:
    def __init__(self, database: Database) -> None:
        self._database = database

    async def record(
        self,
        *,
        role_id: str,
        task_id: str,
        model: str,
        confidence: float,
        explanation: str,
    ) -> None:
        try:
            async with self._database.connection() as conn:
                await conn.execute(
                    """
                    INSERT INTO reasoning (id, created_at, role_id, task_id, model, confidence, explanation)
                    VALUES (lower(hex(randomblob(16))), datetime('now'), ?, ?, ?, ?, ?)
                    """,
                    (role_id, task_id, model, confidence, explanation),
                )
                await conn.commit()
        except Exception as exc:  # pragma: no cover
            logger.warning("Failed to persist reasoning: %s", exc)
