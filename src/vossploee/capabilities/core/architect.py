from __future__ import annotations

import re

from vossploee.capabilities.base import AgentModuleSpec, PydanticTaskWorker
from vossploee.capabilities.core.queue_tools import parse_removal_task_ids_from_description
from vossploee.capabilities.core.worker_tool_context import (
    CoreWorkerToolContext,
    reset_core_tool_context,
    set_core_tool_context,
)
from vossploee.capabilities.loader import list_capability_names
from vossploee.config import Settings
from vossploee.models import AgentName, ArchitectPlan, ArchitectTask, TaskQueue, TaskRecord
from vossploee.repository import TaskRepository
from vossploee.tools.registry import resolve_tools


def _capability_ids_mentioned(text: str) -> list[str]:
    """Return installed capability ids that appear as distinct tokens in ``text`` (longest first)."""
    found: list[str] = []
    for name in sorted(list_capability_names(), key=len, reverse=True):
        if re.search(rf"(?<![A-Za-z0-9_]){re.escape(name)}(?![A-Za-z0-9_])", text, re.IGNORECASE):
            found.append(name)
    return found


async def _enrich_core_removal_plan(
    *,
    parent: TaskRecord,
    plan: ArchitectPlan,
    repository: TaskRepository,
) -> ArchitectPlan:
    """If the LLM emitted ``[Task removal]`` with no UUIDs (e.g. used ``core_queue_list`` and saw no rows), resolve ids from the DB.

    Core's ``core_queue_list`` only shows the **current** capability, so a ``core`` queue01 parent asking to
    remove ``upworkmanager`` roots often yields an empty ``REMOVAL_TASK_IDS`` line unless the model calls
    ``core_queue_list_all``. This fills that gap when capability names appear in the parent request.
    """
    blob = f"{parent.title}\n{parent.description}"
    caps = _capability_ids_mentioned(blob)
    others = [c for c in caps if c != parent.capability_name]
    if len(others) == 1:
        target_caps = others
    elif not others and len(caps) == 1:
        target_caps = caps
    else:
        target_caps = []

    new_tasks: list[ArchitectTask] = []
    for at in plan.tasks:
        if "[task removal]" not in (at.title or "").lower():
            new_tasks.append(at)
            continue
        if parse_removal_task_ids_from_description(at.description):
            new_tasks.append(at)
            continue

        if not target_caps:
            new_tasks.append(at)
            continue

        ids: list[str] = []
        for cap in target_caps:
            rows = await repository.list_queue01_tasks(capability_name=cap)
            ids.extend(r.id for r in rows)
        ids = list(dict.fromkeys(ids))
        ids = [i for i in ids if i != parent.id]
        if not ids:
            new_tasks.append(at)
            continue
        tail = "\n".join(at.description.splitlines()[1:])
        head = f"REMOVAL_TASK_IDS: {','.join(ids)}"
        new_desc = head if not tail.strip() else f"{head}\n{tail}"
        new_tasks.append(at.model_copy(update={"description": new_desc}))

    return ArchitectPlan(tasks=new_tasks)


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
                    "You have `core_queue_list` (queue01 roots for **this** capability only — "
                    "for a `core` root it lists **only** `capability_name=core` rows) and "
                    "`core_queue_list_all` (every capability; each line includes `capability=`). "
                    "**Never** infer that there are “no upworkmanager (or other) roots” from "
                    "`core_queue_list` alone — that tool cannot see them. For any removal/cleanup of "
                    "another capability’s queue01 roots, you **must** call `core_queue_list_all` (optionally "
                    "with a search string), then copy real `id=` values into `REMOVAL_TASK_IDS`. "
                    "Use `core_queue_list` only when the user’s ask is confined to **core**’s own queue.\n\n"
                    "Task removal: when the user asks to remove, cancel, or delete queued work "
                    "(e.g. all tasks, tasks scheduled for today, or specific titles), call the right "
                    "list tool, pick matching queue01 root ids (never guess UUIDs). Compare "
                    "`scheduled_at` in the listing to the user's date criteria using **UTC** (the prompt "
                    "includes current UTC). Never include the current queue01 root id (given in the user "
                    "message) in the removal set—that id is the request you are processing. Output "
                    "**exactly one** queue02 task with title `[Task removal]` and a description whose "
                    "**first line** is exactly:\n"
                    "`REMOVAL_TASK_IDS: <comma-separated-uuid-list>`\n"
                    "Optionally add a second line explaining what was removed. Do not create other queue02 "
                    "tasks for the same removal request.\n\n"
                    "Scheduling: if the work is not meant to run immediately but at a specific future "
                    "time, set `scheduled_at` on that queue02 task to that moment in UTC (ISO-8601). "
                    "Always normalize/translate any user-provided local time (e.g. CEST, PST) to UTC "
                    "before writing `scheduled_at`; never copy local-time values as-is. "
                    "Echo the same UTC instant in the queue02 title or description (e.g. send at "
                    "2026-04-13T15:55:00+00:00) so the Implementer can execute without re-deriving zones. "
                    "Omit `scheduled_at` when the action should run as soon as the Implementer can claim it. "
                    "Describe the timing in title/description/gherkin when helpful.\n\n"
                    "Optional on each queue02 task: set `queue_policy` to `lifo` when that action must run "
                    "before older fifo queue02 work (e.g. urgent removal). Default is `fifo`.\n\n"
                    "The Implementer runs tools (e.g. email) on queue02."
                ),
                tools=resolve_tools(["core.queue_list", "core.queue_list_all"]),
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
                f"Current queue01 root id (never delete this id in REMOVAL_TASK_IDS): {task.id}\n"
                "If the user asks to remove or clear queue01 work **for another capability** "
                "(e.g. upworkmanager), call `core_queue_list_all` — not `core_queue_list` — before "
                "writing REMOVAL_TASK_IDS.\n"
                f"Title: {task.title}\n"
                f"Description: {task.description}"
            )
            plan = await _enrich_core_removal_plan(parent=task, plan=plan, repository=repository)
            await repository.create_child_tasks(parent=task, tasks=plan.tasks)
            await repository.complete_task(
                task.id,
                result=f"Planner created {len(plan.tasks)} doable queue02 action(s).",
            )
        finally:
            reset_core_tool_context(token)
