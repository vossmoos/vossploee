from __future__ import annotations

from pydantic import BaseModel, Field

from vossploee.models import BaseRoleOutput, DecomposedPlan, DecomposerVerdict, RoleTask, TaskRecord, UserRef
from vossploee.roles.base import DecomposerProtocol, PydanticRole, RoleContext, completed, failed


class DecomposerOutput(BaseRoleOutput):
    verdict: DecomposerVerdict
    roots: list[RoleTask] = Field(default_factory=list)
    reply_text: str | None = None


class CoreDecomposer(PydanticRole, DecomposerProtocol):
    role_id = "core.decomposer"
    tools = ("core.memory_recall",)

    def __init__(self, *, app_whoami: str, capability_whoami: str) -> None:
        super().__init__(
            app_whoami=app_whoami,
            capability_whoami=capability_whoami,
            role_prompt=(
                "You are the entrypoint decomposer. Decide verdict: task/reply/noise. "
                "When task, emit role_id values from the loaded catalog."
            ),
        )

    async def decompose(self, *, description: str, requester: UserRef | None) -> DecomposedPlan:
        text = (description or "").strip()
        if not text:
            return DecomposedPlan(verdict=DecomposerVerdict.NOISE)
        if text.endswith("?") and len(text.split()) < 20:
            return DecomposedPlan(verdict=DecomposerVerdict.REPLY, reply_text="I can help. Please share more details for execution.")
        low = text.lower()
        if "upwork" in low or ("job" in low and ("search" in low or "find" in low)):
            return DecomposedPlan(
                verdict=DecomposerVerdict.TASK,
                roots=[RoleTask(title="Upwork sourcing request", description=text, role_id="uw.executor")],
            )
        return DecomposedPlan(
            verdict=DecomposerVerdict.TASK,
            roots=[RoleTask(title="Incoming request", description=text, role_id="core.executor")],
        )

    async def handle(self, task: TaskRecord, ctx: RoleContext):
        return completed("Decomposer task handled", "No-op")
