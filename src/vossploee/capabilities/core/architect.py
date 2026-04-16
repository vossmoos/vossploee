from __future__ import annotations

from vossploee.capabilities.base import AgentModuleSpec, PydanticTaskWorker
from vossploee.capabilities.core.worker_tool_context import (
    CoreWorkerToolContext,
    reset_core_tool_context,
    set_core_tool_context,
)
from vossploee.config import Settings
from vossploee.models import AgentName, ArchitectPlan, TaskQueue, TaskRecord
from vossploee.repository import TaskRepository
from vossploee.tools.registry import resolve_tools


class CoreArchitectWorker(PydanticTaskWorker[ArchitectPlan]):
    role_name = AgentName.ARCHITECT
    queue_name = TaskQueue.QUEUE01

    def __init__(self, settings: Settings) -> None:
        super().__init__(
            settings,
            AgentModuleSpec(
                name="core-architect",
                output_type=ArchitectPlan,
                system_prompt=(
                    "You are the Planner for the core capability (not a software architect). "
                    "Read the queue01 business request, clarify intent, and break it into concrete "
                    "doable actions for the Implementer. Each queue02 item must be one clear **executable** "
                    "action they can perform end-to-end (e.g. send an email, draft text, run a check)—not "
                    "necessarily writing or changing code. Prefer a single queue02 task when one "
                    "step is enough; add more only if the business ask truly needs separate actions. "
                    "Do **not** create queue02 tasks that are only planning or conversion work (e.g. "
                    "'convert CEST to UTC', 'figure out the schedule', 'compute the timestamp')—you do "
                    "that here; the Implementer must receive the **concrete** action (e.g. send this email "
                    "at this UTC time) with times already resolved.\n\n"
                    "Use the gherkin field as a short Given/When/Then-style outline of how to execute "
                    "that action, when helpful.\n\n"
                    "You have the tool `core_queue_list`: use it to list or search existing queue01 "
                    "tasks when you need context about what is already queued.\n\n"
                    "Scheduling: if the work is not meant to run immediately but at a specific future "
                    "time, set `scheduled_at` on that queue02 task to that moment in UTC (ISO-8601). "
                    "Always normalize/translate any user-provided local time (e.g. CEST, PST) to UTC "
                    "before writing `scheduled_at`; never copy local-time values as-is. "
                    "Echo the same UTC instant in the queue02 title or description (e.g. send at "
                    "2026-04-13T15:55:00+00:00) so the Implementer can execute without re-deriving zones. "
                    "Omit `scheduled_at` when the action should run as soon as the Implementer can claim it. "
                    "Describe the timing in title/description/gherkin when helpful.\n\n"
                    "The Implementer runs tools (e.g. email) on queue02."
                ),
                tools=resolve_tools(["core.queue_list"]),
            ),
            capability_name="core",
            include_capability_tools=False,
        )

    async def handle(self, *, task: TaskRecord, repository: TaskRepository) -> None:
        token = set_core_tool_context(
            CoreWorkerToolContext(repository, task.capability_name, None)
        )
        try:
            plan = await self.run_prompt(
                "Turn this business request into doable queue02 action(s) for the Implementer "
                "(title, description, optional Gherkin outline, and optional scheduled_at UTC per task).\n"
                f"Capability: {task.capability_name}\n"
                f"Title: {task.title}\n"
                f"Description: {task.description}"
            )
            await repository.create_child_tasks(parent=task, tasks=plan.tasks)
            await repository.complete_task(
                task.id,
                result=f"Planner created {len(plan.tasks)} doable queue02 action(s).",
            )
        finally:
            reset_core_tool_context(token)
