from __future__ import annotations

import asyncio
import hashlib
from typing import Any

from fastapi import APIRouter, Query

from vossploee.channels.base import Channel
from vossploee.models import Message, UserRef


class EmailChannel(Channel):
    id = "email"
    description = "Email channel with IMAP polling and SMTP sending."

    def __init__(self, *, settings, app_state) -> None:
        self.settings = settings
        self.app_state = app_state
        self._task: asyncio.Task[None] | None = None

    def _allowed(self, email: str) -> bool:
        allow = {x.lower() for x in self.settings.channel_email_allowed_senders}
        return email.lower() in allow

    def user_from_email(self, email: str) -> UserRef:
        digest = hashlib.sha256(email.lower().encode("utf-8")).hexdigest()[:32]
        return UserRef(user_id=f"email:{digest}", channel_id="email", external_id=email.lower())

    async def readfrom(self, user: UserRef, n: int) -> list[Message]:
        return await self.app_state.channel_repo.list_messages(channel_id=self.id, user_id=user.user_id, n=n)

    async def pushto(self, user: UserRef, message: dict[str, Any], task_id: str | None = None) -> Message:
        if not self._allowed(user.external_id):
            raise PermissionError(f"Recipient {user.external_id!r} is not in the allowlist.")
        # Transport send is intentionally omitted; history is still persisted.
        bot = UserRef(user_id="agent", channel_id="email", external_id="agent@local")
        return await self.app_state.channel_repo.create_message(
            channel_id=self.id,
            sender=bot,
            receiver=user,
            body=message,
            task_id=task_id,
        )

    async def poll_once(self) -> list[Message]:
        # Hook point for real IMAP polling; currently no-op unless custom code pushes via API.
        return []

    async def _poll_loop(self) -> None:
        while True:
            await self.poll_once()
            await asyncio.sleep(self.settings.channel_email_poll_seconds)

    async def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._poll_loop(), name="email-poller")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            self._task = None

    def router(self) -> APIRouter:
        router = APIRouter(prefix="/api/channels/email", tags=["channels:email"])

        @router.get("/messages", response_model=list[Message])
        async def list_messages(user: str = Query(...), n: int = Query(50, ge=1, le=500)) -> list[Message]:
            return await self.app_state.channel_repo.list_messages(channel_id=self.id, user_id=user, n=n)

        @router.post("/poll", response_model=list[Message])
        async def poll_now() -> list[Message]:
            return await self.poll_once()

        return router
