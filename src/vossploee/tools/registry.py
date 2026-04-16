from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from pydantic_ai.tools import Tool

_QUALIFIED_TOOLS: dict[str, Tool[Any]] = {}


def qualified_tool_llm_name(qualified_id: str) -> str:
    """Stable name exposed to the model (avoid dots in provider function names)."""
    return qualified_id.replace(".", "_")


def register_tool(
    qualified_id: str,
    function: Callable[..., Any],
    *,
    description: str | None = None,
) -> None:
    """Register a pydantic-ai Tool under a `namespace.tool` id (e.g. `core.imap`)."""
    if qualified_id in _QUALIFIED_TOOLS:
        raise ValueError(f"Tool '{qualified_id}' is already registered.")
    if "." not in qualified_id:
        raise ValueError(
            f"Tool id '{qualified_id}' must be qualified as '<capability_namespace>.<tool_name>'."
        )
    llm_name = qualified_tool_llm_name(qualified_id)
    _QUALIFIED_TOOLS[qualified_id] = Tool(
        function,
        name=llm_name,
        description=description,
    )


def is_registered(qualified_id: str) -> bool:
    return qualified_id in _QUALIFIED_TOOLS


def resolve_tools(qualified_ids: Sequence[str]) -> tuple[Tool[Any], ...]:
    missing = [q for q in qualified_ids if q not in _QUALIFIED_TOOLS]
    if missing:
        known = ", ".join(sorted(_QUALIFIED_TOOLS)) or "<none>"
        raise KeyError(
            f"Unknown tool id(s): {', '.join(missing)}. Registered tools: {known}."
        )
    return tuple(_QUALIFIED_TOOLS[q] for q in qualified_ids)


def registered_qualified_ids() -> frozenset[str]:
    return frozenset(_QUALIFIED_TOOLS.keys())
