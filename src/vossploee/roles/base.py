from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, ClassVar, Protocol

from pydantic import BaseModel
from pydantic_ai import Agent

from vossploee.memory.injector import MemoryInjector
from vossploee.models import BaseRoleOutput, DecomposedPlan, RoleTask, TaskRecord, UserRef
from vossploee.whoami import compose_role_system_prompt


class RoleOutcome(BaseModel):
    kind: str
    summary: str | None = None
    artifact: str | None = None
    error: str | None = None
    children: list[RoleTask] = []
    until: datetime | None = None
    user: UserRef | None = None
    question: dict[str, Any] | None = None


@dataclass(slots=True)
class RoleContext:
    repository: Any
    channels: dict[str, Any]
    tool_registry: Any
    settings: Any
    memory_injector: MemoryInjector
    reasoning_recorder: Any


class Role(ABC):
    role_id: ClassVar[str]

    @abstractmethod
    async def handle(self, task: TaskRecord, ctx: RoleContext) -> RoleOutcome: ...


class DecomposerProtocol(Protocol):
    role_id: str
    async def handle(self, task: TaskRecord, ctx: RoleContext) -> RoleOutcome: ...
    async def decompose(self, *, description: str, requester: UserRef | None) -> DecomposedPlan: ...


class PydanticRole(Role):
    output_type: type[BaseRoleOutput]
    prompt_suffix: str = ""
    tools: tuple[str, ...] = ()
    model: str | None = None

    def __init__(self, *, app_whoami: str, capability_whoami: str, role_prompt: str) -> None:
        self._role_prompt = compose_role_system_prompt(
            app_whoami=app_whoami,
            capability_whoami=capability_whoami,
            role_prompt=role_prompt + "\n\n" + self.prompt_suffix,
        )

    async def run_llm(
        self,
        *,
        prompt_body: str,
        ctx: RoleContext,
        task: TaskRecord,
        output_type: type[Any],
    ) -> Any:
        resolved_tools = ctx.tool_registry.resolve_tools(self.tools) if self.tools else ()
        prompt = await ctx.memory_injector.inject(
            prompt_body=prompt_body,
            capability_id=self.role_id.split(".", 1)[0],
        )
        agent = Agent(
            model=self.model or ctx.settings.agent_model,
            output_type=output_type,
            system_prompt=self._role_prompt
            + "\n\nAlways fill `confidence` and `explanation` fields correctly.",
            tools=resolved_tools,
            defer_model_check=True,
        )
        result = await agent.run(prompt)
        output = result.output
        confidence = float(getattr(output, "confidence", 0.5))
        explanation = str(getattr(output, "explanation", "No explanation"))
        if ctx.reasoning_recorder:
            await ctx.reasoning_recorder.record(
                role_id=self.role_id,
                task_id=str(task.id),
                model=self.model or ctx.settings.agent_model,
                confidence=confidence,
                explanation=explanation,
            )
        return output


def completed(summary: str, artifact: str) -> RoleOutcome:
    return RoleOutcome(kind="completed", summary=summary, artifact=artifact)


def failed(error: str) -> RoleOutcome:
    return RoleOutcome(kind="failed", error=error)


def spawn(children: list[RoleTask]) -> RoleOutcome:
    return RoleOutcome(kind="spawn", children=children)


def defer(until: datetime) -> RoleOutcome:
    if until.tzinfo is None:
        until = until.replace(tzinfo=UTC)
    return RoleOutcome(kind="defer", until=until)


def refine_with(user: UserRef, question: dict[str, Any]) -> RoleOutcome:
    return RoleOutcome(kind="refine", user=user, question=question)
