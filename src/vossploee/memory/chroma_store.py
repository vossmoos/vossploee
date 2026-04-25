from __future__ import annotations

import asyncio
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import chromadb
from chromadb.utils.embedding_functions import OpenAIEmbeddingFunction

from vossploee.config import Settings

AGENT_MEMORY_COLLECTION = "agent_memory_te3l"

# Separate collection for newsroom RSS articles (full article text, structured metadata).
NEWSROOM_NEWS_COLLECTION = "newsroom_monitored_te3l"

MEMORY_KEY_MISSING_MSG = (
    "Long-term memory requires an OpenAI API key: set VOSSPLOEE_OPENAI_API_KEY or OPENAI_API_KEY "
    "so embeddings can use text-embedding-3-large."
)

MEMORY_KINDS: frozenset[str] = frozenset(
    {
        "note",
        "preference",
        "outcome",
        "fact",
        "task_result",
        "research",
        "misc",
    }
)

_MAX_DOCUMENT_CHARS = 50_000
_MAX_RECALL = 50

_clients: dict[str, chromadb.PersistentClient] = {}
_collections: dict[str, Any] = {}
_newsroom_collections: dict[str, Any] = {}
_lock = threading.Lock()


def _openai_api_key(settings: Settings) -> str | None:
    """Key from Settings only (env is merged into Settings by pydantic-settings / get_settings)."""
    k = (settings.openai_api_key or "").strip()
    return k or None


def _embedding_function(settings: Settings) -> Any:
    key = _openai_api_key(settings)
    if not key:
        raise ValueError(MEMORY_KEY_MISSING_MSG)
    return OpenAIEmbeddingFunction(api_key=key, model_name="text-embedding-3-large")


def _resolved_chroma_dir(settings: Settings) -> Path:
    path = settings.chroma_path
    if not path.is_absolute():
        path = Path.cwd() / path
    path.mkdir(parents=True, exist_ok=True)
    return path.resolve()


def _chroma_path_key(settings: Settings) -> str:
    return str(_resolved_chroma_dir(settings))


def _get_collection(settings: Settings) -> Any:
    path_key = _chroma_path_key(settings)
    with _lock:
        if path_key not in _collections:
            client = _clients.get(path_key)
            if client is None:
                client = chromadb.PersistentClient(path=path_key)
                _clients[path_key] = client
            ef = _embedding_function(settings)
            _collections[path_key] = client.get_or_create_collection(
                name=AGENT_MEMORY_COLLECTION,
                metadata={"hnsw:space": "cosine"},
                embedding_function=ef,
            )
        return _collections[path_key]


def _get_newsroom_collection(settings: Settings) -> Any:
    path_key = _chroma_path_key(settings)
    with _lock:
        if path_key not in _newsroom_collections:
            client = _clients.get(path_key)
            if client is None:
                client = chromadb.PersistentClient(path=path_key)
                _clients[path_key] = client
            ef = _embedding_function(settings)
            _newsroom_collections[path_key] = client.get_or_create_collection(
                name=NEWSROOM_NEWS_COLLECTION,
                metadata={"hnsw:space": "cosine"},
                embedding_function=ef,
            )
        return _newsroom_collections[path_key]


def _remember_sync(
    *,
    settings: Settings,
    capability_id: str,
    memory_kind: str,
    text: str,
) -> tuple[str, str]:
    """Returns (memory_id, message)."""
    if memory_kind not in MEMORY_KINDS:
        allowed = ", ".join(sorted(MEMORY_KINDS))
        raise ValueError(f"memory_kind must be one of: {allowed}")
    body = text.strip()
    if not body:
        raise ValueError("text must be non-empty.")
    if len(body) > _MAX_DOCUMENT_CHARS:
        body = body[:_MAX_DOCUMENT_CHARS]
    created = datetime.now(UTC).replace(microsecond=0).isoformat()
    memory_id = str(uuid.uuid4())
    meta: dict[str, Any] = {
        "capability_id": capability_id,
        "memory_kind": memory_kind,
        "created": created,
    }
    col = _get_collection(settings)
    col.add(ids=[memory_id], documents=[body], metadatas=[meta])
    return memory_id, f"Stored memory id={memory_id} (capability={capability_id!r}, kind={memory_kind!r})."


def _recall_sync(
    *,
    settings: Settings,
    capability_id: str,
    query: str,
    top_k: int,
    memory_kind: str | None,
) -> str:
    q = query.strip()
    if not q:
        return "Empty query; pass a natural-language topic to search for."
    k = max(1, min(int(top_k), _MAX_RECALL))
    where: dict[str, Any] | None
    if memory_kind is not None:
        mk = memory_kind.strip()
        if mk not in MEMORY_KINDS:
            allowed = ", ".join(sorted(MEMORY_KINDS))
            return f"Unknown memory_kind {mk!r}. Use one of: {allowed}."
        where = {
            "$and": [
                {"capability_id": capability_id},
                {"memory_kind": mk},
            ]
        }
    else:
        where = {"capability_id": capability_id}

    col = _get_collection(settings)
    res = col.query(query_texts=[q], n_results=k, where=where)
    ids_batch = res.get("ids") or []
    docs_batch = res.get("documents") or []
    meta_batch = res.get("metadatas") or []
    dist_batch = res.get("distances") or []
    if not ids_batch or not ids_batch[0]:
        return "No memories matched (empty store or no similar rows for this capability)."

    ids = ids_batch[0]
    docs = docs_batch[0] if docs_batch else []
    metas = meta_batch[0] if meta_batch else []
    dists = dist_batch[0] if dist_batch else []

    lines: list[str] = [f"Recall ({len(ids)} hit(s), capability={capability_id!r}):"]
    for i, mid in enumerate(ids):
        meta = metas[i] if i < len(metas) else {}
        doc = docs[i] if i < len(docs) else ""
        dist = dists[i] if i < len(dists) else None
        dist_s = f"{dist:.4f}" if isinstance(dist, (int, float)) else "n/a"
        mk = (meta or {}).get("memory_kind", "?")
        cr = (meta or {}).get("created", "?")
        excerpt = doc if len(doc) <= 4000 else doc[:4000] + "\n…(truncated for tool output)"
        lines.append(
            f"\n---\nid={mid} distance={dist_s} memory_kind={mk!r} created={cr!r}\n{excerpt}"
        )
    return "\n".join(lines)


async def remember_document(
    *,
    settings: Settings,
    capability_id: str,
    memory_kind: str,
    text: str,
) -> tuple[str, str]:
    return await asyncio.to_thread(
        _remember_sync,
        settings=settings,
        capability_id=capability_id,
        memory_kind=memory_kind,
        text=text,
    )


async def recall_documents(
    *,
    settings: Settings,
    capability_id: str,
    query: str,
    top_k: int,
    memory_kind: str | None,
) -> str:
    return await asyncio.to_thread(
        _recall_sync,
        settings=settings,
        capability_id=capability_id,
        query=query,
        top_k=top_k,
        memory_kind=memory_kind,
    )


def _newsroom_add_sync(
    *,
    settings: Settings,
    doc_id: str,
    document: str,
    metadata: dict[str, Any],
) -> None:
    body = document.strip()
    if not body:
        raise ValueError("document must be non-empty.")
    if len(body) > _MAX_DOCUMENT_CHARS:
        body = body[:_MAX_DOCUMENT_CHARS]
    col = _get_newsroom_collection(settings)
    meta = {k: ("" if v is None else str(v)) for k, v in metadata.items()}
    col.upsert(ids=[doc_id], documents=[body], metadatas=[meta])


def _newsroom_query_sync(
    *,
    settings: Settings,
    query: str,
    top_k: int,
) -> str:
    q = query.strip()
    if not q:
        return "Empty query; pass a natural-language topic to search for."
    k = max(1, min(int(top_k), _MAX_RECALL))
    col = _get_newsroom_collection(settings)
    res = col.query(query_texts=[q], n_results=k)
    ids_batch = res.get("ids") or []
    docs_batch = res.get("documents") or []
    meta_batch = res.get("metadatas") or []
    dist_batch = res.get("distances") or []
    if not ids_batch or not ids_batch[0]:
        return "No news articles matched (empty index or no similar rows)."

    ids = ids_batch[0]
    docs = docs_batch[0] if docs_batch else []
    metas = meta_batch[0] if meta_batch else []
    dists = dist_batch[0] if dist_batch else []

    lines: list[str] = [f"News recall ({len(ids)} hit(s)):"]
    for i, mid in enumerate(ids):
        meta = metas[i] if i < len(metas) else {}
        doc = docs[i] if i < len(docs) else ""
        dist = dists[i] if i < len(dists) else None
        dist_s = f"{dist:.4f}" if isinstance(dist, (int, float)) else "n/a"
        title = (meta or {}).get("title", "?")
        url = (meta or {}).get("url", "?")
        pub = (meta or {}).get("pub_date", "?")
        src = (meta or {}).get("source", "?")
        excerpt = doc if len(doc) <= 4000 else doc[:4000] + "\n…(truncated for tool output)"
        lines.append(
            f"\n---\nid={mid} distance={dist_s}\n"
            f"title={title!r}\nurl={url!r}\npub_date={pub!r}\nsource={src!r}\n{excerpt}"
        )
    return "\n".join(lines)


async def newsroom_index_article(
    *,
    settings: Settings,
    doc_id: str,
    document: str,
    metadata: dict[str, Any],
) -> None:
    await asyncio.to_thread(
        _newsroom_add_sync,
        settings=settings,
        doc_id=doc_id,
        document=document,
        metadata=metadata,
    )


async def newsroom_query_articles(
    *,
    settings: Settings,
    query: str,
    top_k: int,
) -> str:
    return await asyncio.to_thread(
        _newsroom_query_sync,
        settings=settings,
        query=query,
        top_k=top_k,
    )
