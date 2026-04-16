from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path

from vossploee.database import Database
from vossploee.models import AgentName, DecomposedPlan, TaskQueue
from vossploee.repository import TaskRepository


def test_decomposed_plan_legacy_flat_shape() -> None:
    p = DecomposedPlan.model_validate(
        {"title": "t", "description": "d", "capability_name": "core"}
    )
    assert len(p.roots) == 1
    assert p.roots[0].title == "t"
    assert p.roots[0].scheduled_at is None


def test_future_scheduled_queue01_not_claimable_until_time(tmp_path: Path) -> None:
    async def _run() -> None:
        db = Database(tmp_path / "t.db")
        await db.initialize()
        repo = TaskRepository(db)
        future = datetime.now(UTC) + timedelta(hours=2)
        await repo.create_root_task(
            title="later",
            description="x",
            agent_name=AgentName.DECOMPOSER,
            capability_name="core",
            scheduled_at=future,
        )
        claimed = await repo.claim_next_task(
            queue_name=TaskQueue.QUEUE01,
            agent_name=AgentName.ARCHITECT,
            capability_name="core",
        )
        assert claimed is None

    asyncio.run(_run())


def test_immediate_queue01_claimable(tmp_path: Path) -> None:
    async def _run() -> None:
        db = Database(tmp_path / "t.db")
        await db.initialize()
        repo = TaskRepository(db)
        await repo.create_root_task(
            title="now",
            description="y",
            agent_name=AgentName.DECOMPOSER,
            capability_name="core",
            scheduled_at=None,
        )
        claimed = await repo.claim_next_task(
            queue_name=TaskQueue.QUEUE01,
            agent_name=AgentName.ARCHITECT,
            capability_name="core",
        )
        assert claimed is not None
        assert claimed.title == "now"

    asyncio.run(_run())
