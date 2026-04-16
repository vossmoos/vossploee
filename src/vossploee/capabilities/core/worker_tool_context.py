from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any

from vossploee.repository import TaskRepository


@dataclass(frozen=True, slots=True)
class CoreWorkerToolContext:
    repository: TaskRepository
    capability_name: str
    current_task_id: str | None = None


_CTX: ContextVar[CoreWorkerToolContext | None] = ContextVar("core_worker_tool_ctx", default=None)


def get_core_tool_context() -> CoreWorkerToolContext:
    ctx = _CTX.get()
    if ctx is None:
        raise RuntimeError("Core worker tool context is not set.")
    return ctx


def set_core_tool_context(ctx: CoreWorkerToolContext) -> Any:
    return _CTX.set(ctx)


def reset_core_tool_context(token: Any) -> None:
    _CTX.reset(token)
