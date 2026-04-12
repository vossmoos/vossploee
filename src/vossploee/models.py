from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


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


class CreateTaskRequest(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    description: str = Field(min_length=3)


class CapabilityInfo(BaseModel):
    """Metadata for a capability module (from its README and package id)."""

    id: str
    title: str = ""
    description: str = ""
    functionality: str = ""
    readme_markdown: str = ""


class DecomposedTask(BaseModel):
    title: str
    description: str
    capability_name: str = Field(
        description="One of the enabled capability ids (see GET /api/capabilities).",
    )


class ArchitectTask(BaseModel):
    title: str
    description: str
    gherkin: str


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
    gherkin: str | None = None
    result: str | None = None
    created_at: datetime
    updated_at: datetime
    claimed_at: datetime | None = None
    completed_at: datetime | None = None


class TaskTree(TaskRecord):
    children: list["TaskTree"] = Field(default_factory=list)


TaskTree.model_rebuild()
