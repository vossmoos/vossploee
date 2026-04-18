import asyncio
from pathlib import Path

from vossploee.capabilities.core.architect import _enrich_core_removal_plan
from vossploee.capabilities.core.queue_tools import parse_removal_task_ids_from_description
from vossploee.database import Database
from vossploee.models import AgentName, ArchitectPlan, ArchitectTask, TaskQueuePolicy
from vossploee.repository import TaskRepository
from vossploee.task_queue_intent import decomposer_root_should_use_lifo


def test_parse_removal_accepts_only_uuids() -> None:
    u = "aacbfc78-790b-4cbe-a683-4f6fefe50919"
    assert parse_removal_task_ids_from_description(f"REMOVAL_TASK_IDS: {u}") == [u]
    assert parse_removal_task_ids_from_description("REMOVAL_TASK_IDS: No matching roots") == []
    assert parse_removal_task_ids_from_description(f"REMOVAL_TASK_IDS: {u}, not-a-uuid") == [u]


def test_enrich_core_removal_fills_upworkmanager_ids(tmp_path: Path) -> None:
    async def _run() -> None:
        db = Database(tmp_path / "t.db")
        await db.initialize()
        repo = TaskRepository(db)
        parent = await repo.create_root_task(
            title="Remove all upworkmanager tasks from scheduler",
            description="Clear monitoring.",
            agent_name=AgentName.ARCHITECT,
            capability_name="core",
        )
        uw = await repo.create_root_task(
            title="Upwork monitoring run",
            description="x",
            agent_name=AgentName.DECOMPOSER,
            capability_name="upworkmanager",
        )
        plan = ArchitectPlan(
            tasks=[
                ArchitectTask(
                    title="[Task removal] cleanup",
                    description="REMOVAL_TASK_IDS:\nNo matching roots (LLM mistake).",
                    gherkin="Given…",
                    queue_policy=TaskQueuePolicy.FIFO,
                )
            ]
        )
        out = await _enrich_core_removal_plan(parent=parent, plan=plan, repository=repo)
        ids = parse_removal_task_ids_from_description(out.tasks[0].description)
        assert ids == [uw.id]

    asyncio.run(_run())


def test_lifo_hint_for_remove_scheduler() -> None:
    assert decomposer_root_should_use_lifo(
        "Clear monitors",
        "Remove all upworkmanager tasks from scheduler",
    )


def test_lifo_hint_false_for_monitoring_fanout() -> None:
    assert not decomposer_root_should_use_lifo(
        "Upwork monitoring run +1h",
        "Check Upwork every hour for new jobs",
    )
