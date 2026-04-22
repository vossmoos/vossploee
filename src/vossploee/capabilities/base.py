from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
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
        return result.output


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
