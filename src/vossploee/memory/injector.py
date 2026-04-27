from __future__ import annotations

from typing import Any

from vossploee.config import Settings


class MemoryInjector:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def inject(self, *, prompt_body: str, capability_id: str) -> str:
        hits = await recall_context(
            settings=self._settings,
            query=prompt_body,
            top_k=self._settings.memory_inject_top_k,
            capability_id=capability_id,
        )
        if not hits:
            return "<prior_experience />\n\n" + prompt_body
        lines = [
            '<prior_experience note="Context from your long-term memory. '
            'Do NOT include it in the answer. Use only if it affects your reasoning.">'
        ]
        lines.extend(hits)
        lines.append("</prior_experience>")
        return "\n".join(lines) + "\n\n" + prompt_body


async def recall_context(
    *,
    settings: Settings,
    query: str,
    top_k: int,
    capability_id: str,
) -> list[str]:
    try:
        from vossploee.memory.chroma_store import _get_collection  # type: ignore[attr-defined]
    except Exception:
        return []
    try:
        col = _get_collection(settings)
        result = col.query(query_texts=[query], n_results=top_k)
    except Exception:
        return []
    docs_batch = result.get("documents") or []
    meta_batch = result.get("metadatas") or []
    dist_batch = result.get("distances") or []
    docs = docs_batch[0] if docs_batch else []
    metas = meta_batch[0] if meta_batch else []
    dists = dist_batch[0] if dist_batch else []
    out: list[str] = []
    for idx, doc in enumerate(docs):
        meta: dict[str, Any] = metas[idx] if idx < len(metas) and isinstance(metas[idx], dict) else {}
        dist = dists[idx] if idx < len(dists) else None
        role = str(meta.get("role_id", "?"))
        kind = str(meta.get("kind", meta.get("memory_kind", "?")))
        date = str(meta.get("created_at", meta.get("created", "?")))[:10]
        text = (doc or "")[:800]
        score = f"{float(dist):.2f}" if isinstance(dist, (int, float)) else "n/a"
        out.append(f"- [distance={score} | kind={kind} | role={role} | {date}] {text}")
    return out
