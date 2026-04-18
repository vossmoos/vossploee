from __future__ import annotations

from vossploee.capabilities.base import AgentModuleSpec, PydanticTaskWorker
from vossploee.capabilities.core.queue_tools import parse_removal_task_ids_from_description
from vossploee.capabilities.core.worker_tool_context import (
    CoreWorkerToolContext,
    reset_core_tool_context,
    set_core_tool_context,
)
from vossploee.config import Settings
from vossploee.models import AgentName, ImplementationResult, TaskQueue, TaskRecord, TaskStatus
from vossploee.repository import TaskRepository


class CoreImplementerWorker(PydanticTaskWorker[ImplementationResult]):
    role_name = AgentName.IMPLEMENTER
    queue_name = TaskQueue.QUEUE02

    def __init__(self, settings: Settings) -> None:
        super().__init__(
            settings,
            AgentModuleSpec(
                name="core-implementer",
                output_type=ImplementationResult,
                system_prompt=(
                    "You are the Implementer for the core capability. Your job is to actually "
                    "carry out the queue02 action: do the work, not describe hypothetical code. "
                    "That may mean using tools (e.g. email), writing the requested text, validating "
                    "something, or any other concrete step the Planner asked for—software changes are "
                    "only one possible kind of outcome.\n\n"
                    "Time and scheduling (UTC): the prompt includes the current date and time and may "
                    "include `scheduled_at` from the Planner. That field is the authoritative UTC instant "
                    "when this task was meant to become runnable—compare it to current UTC. If "
                    "`scheduled_at` is absent or current UTC is at or after `scheduled_at`, execute the "
                    "work now (e.g. send the email). Do **not** call `core_queue_defer` in that case.\n\n"
                    "Defer only when the required action time is still **strictly** in the future relative "
                    "to current UTC. Then call `core_queue_defer` with that **exact** future UTC instant "
                    "(from task text or `scheduled_at`). Never defer by rolling forward one minute at a "
                    "time, never use 'now + 1 minute', and never defer repeatedly to slide the time—doing "
                    "that causes an infinite defer loop.\n\n"
                    "Deletion: read the Planner’s task. If title is `[Task removal]` or the description "
                    "contains `REMOVAL_TASK_IDS:` with comma-separated queue01 root ids, call "
                    "`core_queue_delete_batch_resolved` with those ids (deletes roots for **any** "
                    "capability). For a single id you may use `core_queue_delete` only when that id "
                    "belongs to the current capability; otherwise prefer `core_queue_delete_batch_resolved`. "
                    "Parse ids from the Planner’s text yourself; do not delete without explicit ids. "
                    "If no deletion was requested, do not call delete tools.\n\n"
                    "Respond with a short summary of what you did and an artifact field that captures "
                    "the real output (sent message, drafted content, result of a check, etc.). If you "
                    "only deferred or deleted, explain that in summary and put details in artifact.\n\n"
                    "You have `core_imap` (send email via SMTP): use it when the task requires sending mail. "
                    "The recipient is fixed by the system; you only supply subject and body. "
                    "If the task does not require email, do not call it."
                ),
            ),
            capability_name="core",
        )

    async def handle(self, *, task: TaskRecord, repository: TaskRepository) -> None:
        token = set_core_tool_context(
            CoreWorkerToolContext(repository, task.capability_name, task.id)
        )
        try:
            sched = (
                task.scheduled_at.isoformat()
                if task.scheduled_at is not None
                else "not set (run as soon as claimed)"
            )
            result = await self.run_prompt(
                "The Planner left you a single queue02 task. Read title, description, and Gherkin; "
                "decide which tools apply, then execute.\n"
                f"Capability: {task.capability_name}\n"
                f"Title: {task.title}\n"
                f"Description: {task.description}\n"
                f"scheduled_at (UTC from Planner, when this task becomes runnable): {sched}\n"
                "Compare scheduled_at to the current UTC time in the context above. If scheduled_at is "
                "not set or current UTC is at or after it, perform the action now; do not defer.\n"
                f"Execution outline (Gherkin):\n{task.gherkin or ''}"
            )
            removal_ids = parse_removal_task_ids_from_description(task.description)
            if removal_ids:
                still = [tid for tid in removal_ids if await repository.get_task(tid) is not None]
                if still:
                    ok_n, msgs = await repository.delete_queue01_roots_by_ids(task_ids=still)
                    result = ImplementationResult(
                        summary=(
                            f"{result.summary}\n\nPost-check: applied deletion for {ok_n} queue01 root(s) "
                            "that were still present."
                        ),
                        artifact=f"{result.artifact}\n\n---\nDeletion log:\n" + "\n".join(msgs),
                    )
            refreshed = await repository.get_task(task.id)
            if refreshed is None:
                return
            if (
                refreshed.status == TaskStatus.PENDING
                and refreshed.scheduled_at is not None
            ):
                # `core_queue_defer` already returned this task to the queue until scheduled_at.
                return
            await repository.complete_task(
                task.id,
                result=f"{result.summary}\n\nArtifact:\n{result.artifact}",
            )
        finally:
            reset_core_tool_context(token)
