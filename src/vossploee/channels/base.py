from __future__ import annotations

from abc import ABC

from fastapi import APIRouter

from vossploee.models import Message, UserRef


class Channel(ABC):
    id: str
    description: str = ""

    async def readfrom(self, user: UserRef, n: int) -> list[Message]:
        raise NotImplementedError

    async def pushto(self, user: UserRef, message: dict[str, object], task_id: str | None = None) -> Message:
        raise NotImplementedError

    async def poll_once(self) -> list[Message]:
        return []

    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None

    def router(self) -> APIRouter | None:
        return None
