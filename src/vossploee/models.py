from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator


class AgentName(StrEnum):
    DECOMPOSER = "Decomposer"
    ARCHITECT = "Architect"
    IMPLEMENTER = "Implementer"


class TaskQueue(StrEnum):
    QUEUE01 = "queue01"
    QUEUE02 = "queue02"


class TaskKind(StrEnum):
    BUSINESS = "business"
    GHERKIN = "gherkin"


class TaskStatus(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class TaskQueuePolicy(StrEnum):
    """How pending tasks are ordered when claimed (per queue + capability).

    ``fifo`` (default): oldest pending task first.
    ``lifo``: among tasks explicitly tagged LIFO, newest first; **all** pending LIFO tasks are
    claimed before **any** pending FIFO task for the same queue and capability.
    """

    FIFO = "fifo"
    LIFO = "lifo"


class CreateTaskRequest(BaseModel):
    """Single natural-language input; the decomposer derives title, description, and capability."""

    description: str = Field(min_length=3, max_length=50_000)


class CapabilityInfo(BaseModel):
    """Metadata for a capability module (from its README and package id)."""

    id: str
    title: str = ""
    description: str = ""
    functionality: str = ""
    readme_markdown: str = ""
    model_override: str | None = Field(
        default=None,
        description="LLM model from capability config.toml; None means use VOSSPLOEE_AGENT_MODEL.",
    )
    tools: list[str] = Field(
        default_factory=list,
        description="Qualified tool ids enabled for this capability (namespace.tool).",
    )


class DecomposedRootTask(BaseModel):
    """One queue01 root task produced by the Decomposer (optionally scheduled)."""

    title: str
    description: str
    capability_name: str = Field(
        description="One of the enabled capability ids (see GET /api/capabilities).",
    )
    queue_policy: TaskQueuePolicy = Field(
        default=TaskQueuePolicy.FIFO,
        description=(
            "Claim order: fifo (default) or lifo. Use lifo when this root must run before older "
            "routine work (e.g. cancel/clear queue, urgent override)."
        ),
    )
    scheduled_at: datetime | None = Field(
        default=None,
        description=(
            "When this queue01 root becomes runnable (UTC). Omit for 'as soon as possible'. "
            "Use for recurring monitoring: one root per run with staggered times."
        ),
    )

    @field_validator("scheduled_at")
    @classmethod
    def normalize_root_scheduled_at_utc(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


class DecomposedPlan(BaseModel):
    """Decomposer output: one or more queue01 roots (e.g. hourly monitoring runs)."""

    roots: list[DecomposedRootTask] = Field(min_length=1, max_length=500)

    @model_validator(mode="before")
    @classmethod
    def _legacy_single_root(cls, data: object) -> object:
        if isinstance(data, dict) and "roots" not in data:
            if "title" in data and "description" in data and "capability_name" in data:
                return {"roots": [data]}
        return data


# Backwards-compatible alias for the old flat shape (also accepted via DecomposedPlan validator).
DecomposedTask = DecomposedRootTask


class ArchitectTask(BaseModel):
    title: str
    description: str
    gherkin: str
    queue_policy: TaskQueuePolicy = Field(
        default=TaskQueuePolicy.FIFO,
        description="queue02 claim order for this action: fifo (default) or lifo (see TaskQueuePolicy).",
    )
    scheduled_at: datetime | None = Field(
        default=None,
        description=(
            "When this queue02 action must first become runnable (UTC). Omit for 'as soon as possible'. "
            "Use when the work is not for right now but for a specific future time."
        ),
    )

    @field_validator("scheduled_at")
    @classmethod
    def normalize_scheduled_at_utc(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


class ArchitectPlan(BaseModel):
    tasks: list[ArchitectTask]


class ImplementationResult(BaseModel):
    summary: str
    artifact: str


class TaskRecord(BaseModel):
    id: str
    parent_id: str | None = None
    root_id: str
    title: str
    description: str
    queue_name: TaskQueue
    task_kind: TaskKind
    status: TaskStatus
    agent_name: AgentName
    capability_name: str
    queue_policy: TaskQueuePolicy = TaskQueuePolicy.FIFO
    gherkin: str | None = None
    result: str | None = None
    created_at: datetime
    updated_at: datetime
    claimed_at: datetime | None = None
    completed_at: datetime | None = None
    scheduled_at: datetime | None = Field(
        default=None,
        description="If set (UTC), the task is not claimable until this time.",
    )

    @field_validator(
        "created_at",
        "updated_at",
        "claimed_at",
        "completed_at",
        "scheduled_at",
    )
    @classmethod
    def normalize_task_datetimes_utc(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


class TaskTree(TaskRecord):
    children: list["TaskTree"] = Field(default_factory=list)


TaskTree.model_rebuild()


class TaskLogEntry(BaseModel):
    """Archived task tree (full JSON snapshot) moved from `tasks` when a root workflow finishes."""

    id: str
    root_id: str
    capability_name: str
    payload: dict[str, Any]
    created_at: datetime
