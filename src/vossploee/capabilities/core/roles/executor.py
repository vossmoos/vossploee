from __future__ import annotations

from pydantic import BaseModel

from vossploee.models import BaseRoleOutput, TaskRecord
from vossploee.roles.base import PydanticRole, RoleContext, completed


class ExecutorOutput(BaseRoleOutput):
    summary: str
    artifact: str


class CoreExecutor(PydanticRole):
    role_id = "core.executor"
    tools = ("core.memory_remember", "core.memory_recall", "core.imap")

    def __init__(self, *, app_whoami: str, capability_whoami: str) -> None:
        super().__init__(
            app_whoami=app_whoami,
            capability_whoami=capability_whoami,
            role_prompt="You execute generic tasks and return concise outcomes.",
        )

    async def handle(self, task: TaskRecord, ctx: RoleContext):
        text = f"Task: {task.title}\n\n{task.description}\n\nPayload: {task.payload}"
        # Safe fallback execution even without model credentials.
        if not (ctx.settings.openai_api_key or "").strip():
            artifact = f"Executed in fallback mode: {text[:400]}"
            return completed("Task completed without LLM", artifact)
        output = await self.run_llm(prompt_body=text, ctx=ctx, task=task, output_type=ExecutorOutput)
        return completed(output.summary, output.artifact)
