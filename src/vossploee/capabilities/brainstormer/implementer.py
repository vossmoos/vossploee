from __future__ import annotations

from vossploee.capabilities.base import AgentModuleSpec, PydanticTaskWorker
from vossploee.config import Settings
from vossploee.models import AgentName, ImplementationResult, TaskQueue, TaskRecord
from vossploee.repository import TaskRepository


class BrainstormerImplementerWorker(PydanticTaskWorker[ImplementationResult]):
    role_name = AgentName.IMPLEMENTER
    queue_name = TaskQueue.QUEUE02

    def __init__(self, settings: Settings) -> None:
        super().__init__(
            settings,
            AgentModuleSpec(
                name="brainstormer-implementer",
                output_type=ImplementationResult,
                system_prompt=(
                    "You are the Implementer agent for the brainstormer capability. For one idea "
                    "branch, expand it into a useful brief: pros/cons, risks, next validation "
                    "steps, and what a follow-up build might look like. Stay creative and practical; "
                    "this is exploration, not final production code."
                ),
            ),
            capability_name="brainstormer",
        )

    async def handle(self, *, task: TaskRecord, repository: TaskRepository) -> None:
        result = await self.run_prompt(
            "Develop this idea branch into a concise brief.\n"
            f"Capability: {task.capability_name}\n"
            f"Idea title: {task.title}\n"
            f"Notes: {task.description}\n"
            f"Scenario outline:\n{task.gherkin or ''}"
        )
        await repository.complete_task(
            task.id,
            result=f"{result.summary}\n\nArtifact:\n{result.artifact}",
        )
