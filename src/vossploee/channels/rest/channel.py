from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from vossploee.channels.base import Channel
from vossploee.channels.task_ingress import invoke_decomposer
from vossploee.models import Message, UserRef


class RestChannel(Channel):
    id = "rest"
    description = "REST ingress channel without AI triage."

    def __init__(self, *, settings, app_state) -> None:
        self.settings = settings
        self.app_state = app_state
        self._agent_user = UserRef(user_id="agent", channel_id=self.id, external_id="rest:agent")

    async def readfrom(self, user: UserRef, n: int) -> list[Message]:
        return await self.app_state.channel_repo.list_messages(channel_id=self.id, user_id=user.user_id, n=n)

    async def pushto(self, user: UserRef, message: dict[str, Any], task_id: str | None = None) -> Message:
        return await self.app_state.channel_repo.create_message(
            channel_id=self.id,
            sender=self._agent_user,
            receiver=user,
            body=message,
            task_id=task_id,
        )

    def router(self) -> APIRouter:
        router = APIRouter(prefix=f"{self.settings.api_prefix}/channels/rest", tags=["channels:rest"])

        @router.post("/inbound")
        async def inbound(payload: dict[str, Any]) -> dict[str, Any]:
            description = str(payload.get("description", "")).strip()
            sender_payload = payload.get("sender")
            sender = (
                UserRef.model_validate(sender_payload)
                if sender_payload
                else UserRef(user_id="rest:anonymous", channel_id=self.id, external_id="rest:anonymous")
            )
            await self.app_state.channel_repo.create_message(
                channel_id=self.id,
                sender=sender,
                receiver=self._agent_user,
                body={"kind": "inbound", "text": description, "meta": payload.get("meta", {})},
            )
            ingress = await invoke_decomposer(app_state=self.app_state, description=description, requester=sender)
            return {
                "verdict": ingress.verdict.value,
                "reply_text": ingress.reply_text,
                "created_task_ids": [str(task.id) for task in ingress.created],
            }

        return router
