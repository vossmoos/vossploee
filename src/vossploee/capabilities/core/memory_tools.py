from __future__ import annotations

from vossploee.config import get_settings
from vossploee.memory.chroma_store import MEMORY_KINDS, recall_documents, remember_document

async def memory_remember(memory_kind: str, text: str) -> str:
    settings = get_settings()
    kinds = ", ".join(sorted(MEMORY_KINDS))
    try:
        _memory_id, msg = await remember_document(
            settings=settings,
            capability_id="core",
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
    settings = get_settings()
    mk = memory_kind.strip() if memory_kind else None
    if mk == "":
        mk = None
    try:
        return await recall_documents(
            settings=settings,
            capability_id="core",
            query=query,
            top_k=top_k,
            memory_kind=mk,
        )
    except ValueError as exc:
        return f"memory_recall failed: {exc}"
