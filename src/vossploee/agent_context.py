from __future__ import annotations

from datetime import UTC, datetime

from vossploee.memory.chroma_store import MEMORY_KINDS


def format_agent_datetime_context() -> str:
    """Short prefix injected into agent prompts so models can reason about current time."""
    now = datetime.now(UTC)
    return (
        "Current date and time (UTC only, ISO 8601):\n"
        f"- {now.isoformat(timespec='seconds')}\n"
        f"- Date only (UTC): {now.date().isoformat()}\n"
        "- Rule: interpret and output all timestamps in UTC. Convert any local timezone time to UTC before using it."
    )


def with_datetime_context(prompt: str) -> str:
    """Prepend UTC date/time context to a user or task prompt."""
    return f"{format_agent_datetime_context()}\n\n{prompt}"


def format_long_term_memory_tools_blueprint() -> str:
    """How memory works: scope, kinds, tool names. No store access — data only via tools when the model calls them."""
    kinds = ", ".join(sorted(MEMORY_KINDS))
    return (
        "Long-term memory — structure only (nothing from the store is injected here):\n"
        "- Scope: memories are keyed by **capability**; this worker only reads/writes rows for its capability.\n"
        "- Roles: **Architect** and **Implementer** runs each see that same capability slice, not other capabilities.\n"
        "- Tools (only source of stored content): `core_memory_remember` (persist) and `core_memory_recall` "
        "(semantic search).\n"
        f"- Knowledge type / `memory_kind` on remember, optional filter on recall: {kinds}.\n"
        "- Recall: natural-language `query`; optional `memory_kind`; `top_k` defaults to 8 (max 50)."
    )


def with_long_term_memory_tools_blueprint(prompt: str) -> str:
    """Prepend the fixed memory blueprint before the task body (same layering idea as datetime, no DB)."""
    return f"{format_long_term_memory_tools_blueprint()}\n\n{prompt}"
