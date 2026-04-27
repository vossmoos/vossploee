from __future__ import annotations

import json

from pydantic import BaseModel

from vossploee.capabilities.uw.upwork_api_tool import search_recent_upwork_jobs
from vossploee.models import BaseRoleOutput, TaskRecord
from vossploee.roles.base import PydanticRole, RoleContext, completed, failed


class UwExecutorOutput(BaseRoleOutput):
    summary: str
    artifact: str


class UwExecutor(PydanticRole):
    role_id = "uw.executor"
    tools = ("uw.search_jobs", "core.memory_remember", "core.memory_recall")

    def __init__(self, *, app_whoami: str, capability_whoami: str) -> None:
        super().__init__(
            app_whoami=app_whoami,
            capability_whoami=capability_whoami,
            role_prompt=(
                "You execute Upwork sourcing tasks. Extract concise search query, "
                "run search, and summarize opportunities."
            ),
        )

    async def handle(self, task: TaskRecord, ctx: RoleContext):
        query = str(task.payload.get("query") or task.description).strip()
        minutes = int(task.payload.get("minutes", 240))
        limit = int(task.payload.get("limit", 20))
        raw = await search_recent_upwork_jobs(query=query, minutes=minutes, limit=limit)
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return failed(f"Upwork response is not valid JSON: {raw[:300]}")
        if "error" in payload:
            return failed(f"Upwork search failed: {payload.get('message') or payload.get('error')}")
        total = int(payload.get("total_returned", 0))
        summary = f"Found {total} recent Upwork job(s)."
        return completed(summary, raw)
