from __future__ import annotations

from datetime import datetime
from uuid import UUID

from vossploee.capabilities.core.worker_tool_context import get_core_tool_context


def parse_removal_task_ids_from_description(text: str) -> list[str]:
    """Parse ``REMOVAL_TASK_IDS: id1, id2`` line from a task description (Implementer convention).

    Only comma-separated **UUID** tokens count; prose on the same line is ignored.
    """
    for line in (text or "").splitlines():
        stripped = line.strip()
        if stripped.upper().startswith("REMOVAL_TASK_IDS:"):
            rest = stripped.split(":", 1)[1]
            out: list[str] = []
            for p in rest.split(","):
                s = p.strip()
                if not s:
                    continue
                try:
                    out.append(str(UUID(s)))
                except ValueError:
                    continue
            return out
    return []


async def queue_list_queue01(search: str | None = None) -> str:
    """List queue01 (root business) tasks for this capability; optional substring match on title/description."""
    ctx = get_core_tool_context()
    rows = await ctx.repository.list_queue01_tasks(
        capability_name=ctx.capability_name,
        search=search,
    )
    if not rows:
        return "No queue01 tasks match." if search else "No queue01 tasks."

    lines: list[str] = []
    for r in rows:
        sched = f", scheduled_at={r.scheduled_at.isoformat()}" if r.scheduled_at else ""
        lines.append(
            f"- id={r.id} policy={r.queue_policy.value} status={r.status} title={r.title!r} "
            f"description={r.description[:200]!r}{sched}"
        )
    return "\n".join(lines)


async def queue_list_queue01_all_capabilities(search: str | None = None) -> str:
    """List all queue01 root tasks across every capability; optional substring match on title/description."""
    ctx = get_core_tool_context()
    rows = await ctx.repository.list_queue01_tasks_all_capabilities(search=search)
    if not rows:
        return "No queue01 tasks match." if search else "No queue01 tasks."

    lines: list[str] = []
    for r in rows:
        sched = f", scheduled_at={r.scheduled_at.isoformat()}" if r.scheduled_at else ""
        lines.append(
            f"- id={r.id} capability={r.capability_name!r} policy={r.queue_policy.value} "
            f"status={r.status} title={r.title!r} description={r.description[:200]!r}{sched}"
        )
    return "\n".join(lines)


async def queue_delete_queue01(task_id: str) -> str:
    """Remove a queue01 root task and its entire subtree (queue02 children) from the active queues."""
    ctx = get_core_tool_context()
    ok, message = await ctx.repository.delete_queue01_task(
        task_id=task_id.strip(),
        capability_name=ctx.capability_name,
    )
    return message


async def queue_delete_queue01_batch(task_ids: list[str]) -> str:
    """Remove several queue01 root tasks (each with its subtree) for this capability. Duplicates are ignored."""
    ctx = get_core_tool_context()
    if not task_ids:
        return "No task ids provided."
    ok_n, messages = await ctx.repository.delete_queue01_tasks_batch(
        task_ids=task_ids,
        capability_name=ctx.capability_name,
    )
    detail = "\n".join(messages)
    return f"Deleted {ok_n} queue01 root(s) for this capability.\n{detail}"


async def queue_delete_queue01_batch_resolved(task_ids: list[str]) -> str:
    """Remove queue01 roots by id for any capability (each id must be a queue01 root; subtree deleted)."""
    ctx = get_core_tool_context()
    if not task_ids:
        return "No task ids provided."
    ok_n, messages = await ctx.repository.delete_queue01_roots_by_ids(task_ids=task_ids)
    detail = "\n".join(messages)
    return f"Deleted {ok_n} queue01 root(s).\n{detail}"


async def queue_defer_current_queue02(until_iso: str) -> str:
    """Put the current queue02 task back to pending until the given UTC ISO-8601 time (e.g. 2026-04-15T14:30:00+00:00)."""
    ctx = get_core_tool_context()
    if not ctx.current_task_id:
        return "No current task id in context; defer is only available to the Implementer."
    raw = until_iso.strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        until = datetime.fromisoformat(raw)
    except ValueError:
        return (
            "Could not parse datetime. Use ISO-8601 UTC, e.g. 2026-04-15T14:30:00+00:00 "
            f"(received: {until_iso!r})."
        )
    ok, message = await ctx.repository.defer_queue02_task(
        task_id=ctx.current_task_id,
        capability_name=ctx.capability_name,
        until=until,
    )
    return message
