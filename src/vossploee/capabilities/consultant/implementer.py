from __future__ import annotations

from vossploee.capabilities.base import AgentModuleSpec, PydanticTaskWorker
from vossploee.config import Settings
from vossploee.models import AgentName, ImplementationResult, TaskQueue, TaskRecord
from vossploee.repository import TaskRepository


class ConsultantImplementerWorker(PydanticTaskWorker[ImplementationResult]):
    role_name = AgentName.IMPLEMENTER
    queue_name = TaskQueue.QUEUE02

    def __init__(self, settings: Settings) -> None:
        super().__init__(
            settings,
            AgentModuleSpec(
                name="consultant-implementer",
                output_type=ImplementationResult,
                system_prompt=(
                    "You are the Implementer agent for the consultant capability. Produce a "
                    "compact execution summary for a queue02 task and describe the artifact or "
                    "next change that would be delivered. Do not assume any external tools are "
                    "available unless they were explicitly registered."
                ),
            ),
        )

    async def handle(self, *, task: TaskRecord, repository: TaskRepository) -> None:
        result = await self.run_prompt(
            "Produce an implementation summary for this technical task.\n"
            f"Capability: {task.capability_name}\n"
            f"Title: {task.title}\n"
            f"Description: {task.description}\n"
            f"Gherkin:\n{task.gherkin or ''}"
        )
        await repository.complete_task(
            task.id,
            result=f"{result.summary}\n\nArtifact:\n{result.artifact}",
        )
