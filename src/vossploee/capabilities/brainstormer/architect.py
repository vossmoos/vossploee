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


class BrainstormerArchitectWorker(PydanticTaskWorker[ArchitectPlan]):
    role_name = AgentName.ARCHITECT
    queue_name = TaskQueue.QUEUE01

    def __init__(self, settings: Settings) -> None:
        super().__init__(
            settings,
            AgentModuleSpec(
                name="brainstormer-architect",
                output_type=ArchitectPlan,
                system_prompt=(
                    "You are the Architect agent for the brainstormer capability. The user wants "
                    "ideas and solution directions, not a single implementation plan. From a "
                    "queue01 request, propose several distinct solution ideas or approaches. "
                    "For each idea, put a short scenario-style outline in the gherkin field "
                    "(Given/When/Then is fine) that captures how that idea would be explored or validated."
                ),
            ),
            capability_name="brainstormer",
        )

    async def handle(self, *, task: TaskRecord, repository: TaskRepository) -> None:
        token = set_core_tool_context(
            CoreWorkerToolContext(repository, task.capability_name, None, settings=self._settings)
        )
        try:
            plan = await self.run_prompt(
                "Propose multiple solution ideas or approaches for this request. "
                "Each output task is one idea branch for queue02.\n"
                f"Capability: {task.capability_name}\n"
                f"Title: {task.title}\n"
                f"Description: {task.description}"
            )
            await repository.create_child_tasks(parent=task, tasks=plan.tasks)
            await repository.complete_task(
                task.id,
                result=f"Brainstormer architect captured {len(plan.tasks)} idea branch(es).",
            )
        finally:
            reset_core_tool_context(token)
