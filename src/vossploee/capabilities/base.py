from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Generic, TypeVar

from pydantic_ai import Agent
from pydantic_ai.capabilities import AbstractCapability as PydanticAgentCapability

from vossploee.config import Settings
from vossploee.errors import AgentExecutionError
from vossploee.models import AgentName, TaskQueue, TaskRecord

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
    def __init__(self, settings: Settings, spec: AgentModuleSpec[OutputT]) -> None:
        self._model_name = settings.agent_model
        self._role_label = spec.name
        self.agent = Agent(
            model=self._model_name,
            output_type=spec.output_type,
            name=spec.name,
            system_prompt=spec.system_prompt,
            tools=spec.tools,
            capabilities=spec.capabilities,
            defer_model_check=True,
        )

    async def run_prompt(self, prompt: str) -> OutputT:
        if not self._model_name:
            raise AgentExecutionError(f"{self._role_label} agent model is not configured.")

        result = await self.agent.run(prompt)
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
