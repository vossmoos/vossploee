from __future__ import annotations

from vossploee.capabilities.core.imap_tool import imap_send_mail
from vossploee.capabilities.core.memory_tools import memory_recall, memory_remember
from vossploee.capabilities.core.queue_tools import (
    queue_defer_current_queue02,
    queue_delete_queue01,
    queue_delete_queue01_batch,
    queue_delete_queue01_batch_resolved,
    queue_list_queue01,
    queue_list_queue01_all_capabilities,
)
from vossploee.tools.registry import register_tool


def _register() -> None:
    register_tool(
        "core.imap",
        imap_send_mail,
        description=(
            "Send one email when the user needs outbound mail. Uses SMTP (SSL) from core/config.toml "
            "[imap] and credentials from the listed env vars. Recipient is fixed to aol@vossmoos.de only; "
            "pass subject and body."
        ),
    )
    register_tool(
        "core.queue_list",
        queue_list_queue01,
        description=(
            "List active queue01 (root business) tasks for this capability. "
            "Optional search string filters by title or description substring."
        ),
    )
    register_tool(
        "core.queue_list_all",
        queue_list_queue01_all_capabilities,
        description=(
            "List all queue01 root tasks across every capability (each line includes capability=). "
            "Use for platform-wide cleanup or when removing work owned by another capability. "
            "Optional search string filters by title or description substring."
        ),
    )
    register_tool(
        "core.queue_delete",
        queue_delete_queue01,
        description=(
            "Delete a queue01 task by id and remove its entire subtree (all queue02 children). "
            "Use only when the user explicitly instructs removal or cancellation of that queued work."
        ),
    )
    register_tool(
        "core.queue_delete_batch",
        queue_delete_queue01_batch,
        description=(
            "Delete multiple queue01 root tasks by id (each id removes that root and all of its queue02 "
            "children). Use when the Planner listed several ids to remove. Same capability scope as "
            "core.queue_delete."
        ),
    )
    register_tool(
        "core.queue_delete_batch_resolved",
        queue_delete_queue01_batch_resolved,
        description=(
            "Delete queue01 roots by id for any capability (ids must be queue01 roots from "
            "`core.queue_list_all` or similar). Prefer this for `[Task removal]` when ids may belong to "
            "capabilities other than core."
        ),
    )
    register_tool(
        "core.queue_defer",
        queue_defer_current_queue02,
        description=(
            "Defer the current queue02 task: return it to pending until a future UTC time (ISO-8601). "
            "Use when the task must not run until that time (e.g. user-specified datetime not yet reached)."
        ),
    )
    register_tool(
        "core.memory_remember",
        memory_remember,
        description=(
            "Store long-term memory for the current capability. `text` is embedded (OpenAI "
            "text-embedding-3-large when configured) and returned on recall; metadata records capability_id, "
            "memory_kind, and created (UTC). memory_kind must be one of: "
            "note, preference, outcome, fact, task_result, research, misc."
        ),
    )
    register_tool(
        "core.memory_recall",
        memory_recall,
        description=(
            "Semantic search over stored memories for the current capability only (same embedding model as "
            "remember). Pass a natural-language `query` (topic/intent). Optional `memory_kind` filters to "
            "the same enum as remember. `top_k` caps how many hits (default 8, max 50)."
        ),
    )


_register()
