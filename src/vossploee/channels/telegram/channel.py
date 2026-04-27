from __future__ import annotations

import asyncio
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel
from pydantic_ai import Agent

from vossploee.channels.base import Channel
from vossploee.channels.task_ingress import invoke_decomposer
from vossploee.models import Message, UserRef


class TelegramReply(BaseModel):
    reply_text: str


class TelegramChannel(Channel):
    id = "telegram"
    description = "Telegram channel with LLM gatekeeper."

    def __init__(self, *, settings, app_state) -> None:
        self.settings = settings
        self.app_state = app_state
        self._task: asyncio.Task[None] | None = None
        self._offset = 0
        self._agent_user = UserRef(user_id="agent", channel_id=self.id, external_id="telegram:agent")

    async def readfrom(self, user: UserRef, n: int) -> list[Message]:
        return await self.app_state.channel_repo.list_messages(channel_id=self.id, user_id=user.user_id, n=n)

    async def pushto(self, user: UserRef, message: dict[str, Any], task_id: str | None = None) -> Message:
        token = self._bot_token()
        text = str(message.get("text", "")).strip()
        if token and text:
            await self._send_message(token=token, chat_id=user.external_id, text=text)
        return await self.app_state.channel_repo.create_message(
            channel_id=self.id,
            sender=self._agent_user,
            receiver=user,
            body=message,
            task_id=task_id,
        )

    async def poll_once(self) -> list[Message]:
        token = self._bot_token()
        if not token:
            return []
        updates = await self._get_updates(token=token)
        out: list[Message] = []
        for update in updates:
            update_id = int(update.get("update_id", 0))
            if update_id >= self._offset:
                self._offset = update_id + 1
            msg = update.get("message") or {}
            chat = msg.get("chat") or {}
            chat_id = str(chat.get("id", "")).strip()
            text = str(msg.get("text", "")).strip()
            if not chat_id or not text:
                continue
            if not self._allowed(chat_id):
                continue
            sender = UserRef(user_id=f"telegram:{chat_id}", channel_id=self.id, external_id=chat_id)
            inbound = await self.app_state.channel_repo.create_message(
                channel_id=self.id,
                sender=sender,
                receiver=self._agent_user,
                body={"kind": "inbound", "text": text, "meta": {"update_id": update_id}},
                dedupe_key=f"telegram:update:{update_id}",
            )
            out.append(inbound)
            reply_text = await self._run_gatekeeper(sender=sender, text=text)
            if reply_text:
                await self.pushto(sender, {"kind": "reply", "text": reply_text, "meta": {"in_reply_to": str(inbound.id)}})
        return out

    async def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._poll_loop(), name="telegram-poller")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            self._task = None

    def router(self) -> APIRouter:
        router = APIRouter(prefix=f"{self.settings.api_prefix}/channels/telegram", tags=["channels:telegram"])

        @router.get("/messages", response_model=list[Message])
        async def list_messages(user: str = Query(...), n: int = Query(50, ge=1, le=500)) -> list[Message]:
            return await self.app_state.channel_repo.list_messages(channel_id=self.id, user_id=user, n=n)

        @router.post("/poll", response_model=list[Message])
        async def poll_now() -> list[Message]:
            return await self.poll_once()

        return router

    async def _poll_loop(self) -> None:
        while True:
            await self.poll_once()
            await asyncio.sleep(self.settings.channel_telegram_poll_seconds)

    def _allowed(self, chat_id: str) -> bool:
        allow = set(self.settings.channel_telegram_allowed_chat_ids)
        if not allow:
            return True
        return chat_id in allow

    def _bot_token(self) -> str:
        key = (self.settings.channel_telegram_bot_token_env or "").strip()
        if not key:
            return ""
        return (os.getenv(key) or "").strip()

    async def _run_gatekeeper(self, *, sender: UserRef, text: str) -> str:
        if not self.settings.openai_api_key:
            raise RuntimeError(
                "Telegram gatekeeper requires OPENAI_API_KEY (or VOSSPLOEE_OPENAI_API_KEY). "
                "Configure it before using the telegram channel."
            )

        async def invoke_task(description: str) -> str:
            ingress = await invoke_decomposer(app_state=self.app_state, description=description, requester=sender)
            if ingress.verdict == DecomposerVerdict.TASK:
                if ingress.created:
                    return f"Task accepted. I created {len(ingress.created)} task(s)."
                return "Task accepted."
            if ingress.verdict == DecomposerVerdict.REPLY:
                return ingress.reply_text or "I understood your message."
            return "No actionable task was detected."

        agent = Agent(
            model=self.settings.agent_model,
            output_type=TelegramReply,
            system_prompt=(
                "You are the Telegram gatekeeper for Vossploee. "
                "Chat naturally. If and only if the user explicitly asks you to do work/tasks, "
                "call the tool `invoke_task` exactly once. "
                "Then return a friendly reply in `reply_text`."
            ),
            tools=[invoke_task],
            defer_model_check=True,
        )
        result = await agent.run(text)
        return result.output.reply_text.strip()

    async def _get_updates(self, *, token: str) -> list[dict[str, Any]]:
        params = urllib.parse.urlencode({"timeout": 1, "offset": self._offset})
        url = f"https://api.telegram.org/bot{token}/getUpdates?{params}"
        try:
            payload = await asyncio.to_thread(self._http_get_json, url)
        except urllib.error.URLError:
            return []
        result = payload.get("result")
        if isinstance(result, list):
            return [item for item in result if isinstance(item, dict)]
        return []

    async def _send_message(self, *, token: str, chat_id: str, text: str) -> None:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        body = urllib.parse.urlencode({"chat_id": chat_id, "text": text}).encode("utf-8")
        try:
            await asyncio.to_thread(self._http_post, url, body)
        except urllib.error.URLError:
            return

    @staticmethod
    def _http_get_json(url: str) -> dict[str, Any]:
        with urllib.request.urlopen(url, timeout=10) as response:  # noqa: S310
            data = response.read().decode("utf-8")
        parsed = json.loads(data)
        return parsed if isinstance(parsed, dict) else {}

    @staticmethod
    def _http_post(url: str, body: bytes) -> None:
        request = urllib.request.Request(url=url, data=body, method="POST")
        with urllib.request.urlopen(request, timeout=10):  # noqa: S310
            return
