from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
import re
from typing import TYPE_CHECKING, Any, Generic, TypeVar

from pydantic_ai import Agent
from pydantic_ai.capabilities import AbstractCapability as PydanticAgentCapability

from vossploee.agent_context import (
    with_datetime_context,
    with_long_term_memory_tools_blueprint,
)
from vossploee.capabilities.capability_settings import load_capability_settings
from vossploee.config import Settings
from vossploee.errors import AgentExecutionError
from vossploee.models import AgentName, TaskQueue, TaskRecord
from vossploee.tools.registry import resolve_tools

if TYPE_CHECKING:
    from vossploee.repository import TaskRepository

OutputT = TypeVar("OutputT")

_HTTP_STATUS_MATCHERS: tuple[re.Pattern[str], ...] = (
    # Common error text from tools / SDKs.
    re.compile(r"\bHTTP\s+(404|429|5\d\d)\b", re.IGNORECASE),
    re.compile(r"\bHTTP\s+error\s*[:=]?\s*(404|429|5\d\d)\b", re.IGNORECASE),
    re.compile(r"\bstatus(?:\s*code)?\s*[:=]?\s*(404|429|5\d\d)\b", re.IGNORECASE),
    # JSON-style payloads: {"status_code": 500}
    re.compile(r'"status_code"\s*:\s*(404|429|5\d\d)\b', re.IGNORECASE),
)

_TOOL_FAILURE_MATCHERS: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(r"\bGraphQL validation error\b", re.IGNORECASE),
        "graphQL validation failure",
    ),
    (
        re.compile(r"\bmutation field\b.*\bundefined\b", re.IGNORECASE),
        "graphQL mutation is undefined in schema",
    ),
    (
        re.compile(r"\btool error\b", re.IGNORECASE),
        "tool execution error",
    ),
    (
        re.compile(r"\b(?:result|status)\s*:\s*FAILED\b", re.IGNORECASE),
        "tool/action reported FAILED result",
    ),
)


def extract_http_failure_status(text: str) -> int | None:
    """Return an HTTP status we treat as task-failing, or None."""
    for pattern in _HTTP_STATUS_MATCHERS:
        m = pattern.search(text or "")
        if m:
            try:
                return int(m.group(1))
            except (TypeError, ValueError):
                return None
    return None


def summarize_http_failure(text: str) -> str | None:
    """Build a normalized error summary for 404/429/5xx failures."""
    status = extract_http_failure_status(text)
    if status is None:
        return None
    cleaned = " ".join((text or "").split())
    if len(cleaned) > 600:
        cleaned = cleaned[:600] + "..."
    return f"Detected upstream HTTP {status} failure in agent/tool flow. {cleaned}"


def summarize_tool_failure(text: str) -> str | None:
    """Build a normalized error summary for explicit non-HTTP tool failures."""
    cleaned = " ".join((text or "").split())
    if not cleaned:
        return None
    for pattern, reason in _TOOL_FAILURE_MATCHERS:
        if pattern.search(cleaned):
            if len(cleaned) > 600:
                cleaned = cleaned[:600] + "..."
            return f"Detected {reason} in agent/tool flow. {cleaned}"
    return None


@dataclass(frozen=True, slots=True)
class AgentModuleSpec(Generic[OutputT]):
    name: str
    output_type: type[OutputT]
    system_prompt: str | Sequence[str]
    tools: tuple[Any, ...] = ()
    capabilities: tuple[PydanticAgentCapability[Any], ...] = ()


class TaskWorker(ABC):
    role_name: AgentName
    queue_name: TaskQueue

    @abstractmethod
    async def handle(self, *, task: TaskRecord, repository: TaskRepository) -> None:
        """Process one claimed task for this worker."""


class PydanticTaskWorker(TaskWorker, Generic[OutputT], ABC):
    def __init__(
        self,
        settings: Settings,
        spec: AgentModuleSpec[OutputT],
        *,
        capability_name: str,
        include_capability_tools: bool = True,
    ) -> None:
        cap_cfg = load_capability_settings(capability_name)
        self._settings = settings
        self._model_name = cap_cfg.model or settings.model_for_agent(self.role_name)
        self._role_label = spec.name
        capability_tools = (
            resolve_tools(cap_cfg.tools) if include_capability_tools else ()
        )
        combined_tools = tuple(spec.tools) + capability_tools
        tool_names = {getattr(t, "name", None) for t in combined_tools}
        self._memory_tools_blueprint_enabled = (
            "core_memory_recall" in tool_names or "core_memory_remember" in tool_names
        )
        self.agent = Agent(
            model=self._model_name,
            output_type=spec.output_type,
            name=spec.name,
            system_prompt=spec.system_prompt,
            tools=combined_tools,
            capabilities=spec.capabilities,
            defer_model_check=True,
        )

    async def run_prompt(self, prompt: str) -> OutputT:
        if not self._model_name:
            raise AgentExecutionError(f"{self._role_label} agent model is not configured.")

        body = (
            with_long_term_memory_tools_blueprint(prompt)
            if self._memory_tools_blueprint_enabled
            else prompt
        )
        result = await self.agent.run(with_datetime_context(body))
        output = result.output
        text = _output_to_text(output)
        failure = summarize_http_failure(text) or summarize_tool_failure(text)
        if failure:
            raise AgentExecutionError(failure)
        return output


def _output_to_text(output: object) -> str:
    if output is None:
        return ""
    if isinstance(output, str):
        return output
    model_dump = getattr(output, "model_dump", None)
    if callable(model_dump):
        try:
            return repr(model_dump())
        except Exception:
            return repr(output)
    return repr(output)


class CapabilityModule(ABC):
    name: str
    description: str

    @abstractmethod
    def get_architect_worker(self) -> TaskWorker:
        """Return the architect worker for this capability."""

    @abstractmethod
    def get_implementer_worker(self) -> TaskWorker:
        """Return the implementer worker for this capability."""

    def get_workers(self) -> tuple[TaskWorker, TaskWorker]:
        return (self.get_architect_worker(), self.get_implementer_worker())
