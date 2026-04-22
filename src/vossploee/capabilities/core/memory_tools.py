from __future__ import annotations

from typing import TYPE_CHECKING

from vossploee.capabilities.core.worker_tool_context import get_core_tool_context

if TYPE_CHECKING:
    from vossploee.config import Settings

from vossploee.config import get_settings
from vossploee.memory.chroma_store import MEMORY_KINDS, recall_documents, remember_document


def _settings_for_memory() -> "Settings":
    ctx = get_core_tool_context()
    if ctx.settings is not None:
        return ctx.settings
    return get_settings()


async def memory_remember(memory_kind: str, text: str) -> str:
    """Persist searchable long-term memory for this capability (body is embedded; metadata is structured)."""
    ctx = get_core_tool_context()
    settings = _settings_for_memory()
    kinds = ", ".join(sorted(MEMORY_KINDS))
    try:
        _memory_id, msg = await remember_document(
            settings=settings,
            capability_id=ctx.capability_name,
            memory_kind=memory_kind.strip(),
            text=text,
        )
    except ValueError as exc:
        err = str(exc)
        if "memory_kind must be one of:" in err:
            return f"memory_remember rejected: {exc}\nAllowed memory_kind values: {kinds}."
        return f"memory_remember failed: {err}"
    return msg


async def memory_recall(
    query: str,
    top_k: int = 8,
    memory_kind: str | None = None,
) -> str:
    """Semantic search over memories for this capability only; optional filter by memory_kind."""
    ctx = get_core_tool_context()
    settings = _settings_for_memory()
    mk = memory_kind.strip() if memory_kind else None
    if mk == "":
        mk = None
    try:
        return await recall_documents(
            settings=settings,
            capability_id=ctx.capability_name,
            query=query,
            top_k=top_k,
            memory_kind=mk,
        )
    except ValueError as exc:
        return f"memory_recall failed: {exc}"
