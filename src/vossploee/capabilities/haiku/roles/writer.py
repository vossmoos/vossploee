from __future__ import annotations

from pydantic import BaseModel

from vossploee.models import BaseRoleOutput, TaskRecord, UserRef
from vossploee.roles.base import PydanticRole, RoleContext, completed


class HaikuOutput(BaseRoleOutput):
    haiku: str


class HaikuWriter(PydanticRole):
    role_id = "haiku.writer"
    tools = ("core.imap", "core.memory_remember", "core.memory_recall")

    def __init__(self, *, app_whoami: str, capability_whoami: str) -> None:
        super().__init__(
            app_whoami=app_whoami,
            capability_whoami=capability_whoami,
            role_prompt="Write concise beautiful haiku and deliver them by email when asked.",
        )

    async def handle(self, task: TaskRecord, ctx: RoleContext):
        theme = task.description
        if not (ctx.settings.openai_api_key or "").strip():
            poem = f"{theme[:20]}\nsoft wind over logs\nagent hums at dusk"
            return completed("haiku generated", poem)
        output = await self.run_llm(prompt_body=f"Write one haiku about: {theme}", ctx=ctx, task=task, output_type=HaikuOutput)
        return completed("haiku generated", output.haiku)
