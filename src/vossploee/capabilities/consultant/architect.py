from __future__ import annotations

from vossploee.capabilities.base import AgentModuleSpec, PydanticTaskWorker
from vossploee.config import Settings
from vossploee.models import AgentName, ArchitectPlan, TaskQueue, TaskRecord
from vossploee.repository import TaskRepository


class ConsultantArchitectWorker(PydanticTaskWorker[ArchitectPlan]):
    role_name = AgentName.ARCHITECT
    queue_name = TaskQueue.QUEUE01

    def __init__(self, settings: Settings) -> None:
        super().__init__(
            settings,
            AgentModuleSpec(
                name="consultant-architect",
                output_type=ArchitectPlan,
                system_prompt=(
                    "You are the Architect agent for the consultant capability. Turn a business "
                    "task from queue01 into a short set of implementable technical tasks "
                    "expressed in Gherkin notation for queue02. Do not assume any external "
                    "tools are available unless they were explicitly registered."
                ),
            ),
        )

    async def handle(self, *, task: TaskRecord, repository: TaskRepository) -> None:
        plan = await self.run_prompt(
            "Split the following business request into technical tasks and provide Gherkin "
            "for each output task.\n"
            f"Capability: {task.capability_name}\n"
            f"Title: {task.title}\n"
            f"Description: {task.description}"
        )
        await repository.create_child_tasks(parent=task, tasks=plan.tasks)
        await repository.complete_task(
            task.id,
            result=f"Architect created {len(plan.tasks)} queue02 task(s).",
        )
