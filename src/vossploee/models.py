from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class BaseRoleOutput(BaseModel):
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)
    explanation: str = Field(min_length=1, max_length=500, default="No explanation provided.")


class UserRef(BaseModel):
    user_id: str
    channel_id: str
    external_id: str


class TaskStatus(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    REFINING = "refining"


class RoleTask(BaseModel):
    title: str
    description: str
    role_id: str
    scheduled_at: datetime | None = None
    queue_policy: Literal["fifo", "lifo"] = "fifo"
    payload: dict[str, Any] = Field(default_factory=dict)

    @field_validator("scheduled_at")
    @classmethod
    def _normalize_scheduled(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


class DecomposerVerdict(StrEnum):
    TASK = "task"
    REPLY = "reply"
    NOISE = "noise"


class DecomposedPlan(BaseModel):
    verdict: DecomposerVerdict
    roots: list[RoleTask] = Field(default_factory=list)
    reply_text: str | None = None


class TaskRecord(BaseModel):
    id: UUID
    parent_id: UUID | None = None
    root_id: UUID
    role_id: str
    capability_id: str
    title: str
    description: str
    payload: dict[str, Any] = Field(default_factory=dict)
    status: TaskStatus
    queue_policy: Literal["fifo", "lifo"] = "fifo"
    scheduled_at: datetime | None = None
    refining_until_user: UserRef | None = None
    result: str | None = None
    created_at: datetime
    updated_at: datetime
    claimed_at: datetime | None = None
    completed_at: datetime | None = None

    @field_validator(
        "scheduled_at",
        "created_at",
        "updated_at",
        "claimed_at",
        "completed_at",
        mode="before",
    )
    @classmethod
    def _normalize_dt(cls, value: datetime | str | None) -> datetime | None:
        if value is None:
            return None
        dt = value if isinstance(value, datetime) else datetime.fromisoformat(value)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=UTC)
        return dt.astimezone(UTC)


class TaskTree(TaskRecord):
    children: list["TaskTree"] = Field(default_factory=list)


TaskTree.model_rebuild()


class Message(BaseModel):
    id: UUID
    channel_id: str
    sender: UserRef
    receiver: UserRef
    body: dict[str, Any]
    in_reply_to: UUID | None = None
    task_id: UUID | None = None
    created_at: datetime


class CapabilityInfo(BaseModel):
    id: str
    description: str
    roles: list[str]
    tools: list[str]
    whoami: str


class ChannelInfo(BaseModel):
    id: str
    description: str
