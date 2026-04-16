from __future__ import annotations

from datetime import datetime

from vossploee.capabilities.core.worker_tool_context import get_core_tool_context


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
            f"- id={r.id} status={r.status} title={r.title!r} "
            f"description={r.description[:200]!r}{sched}"
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
