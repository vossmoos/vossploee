from __future__ import annotations

from abc import ABC
from collections.abc import Mapping

from fastapi import APIRouter

from vossploee.roles.base import Role


class CapabilityModule(ABC):
    id: str
    description: str

    def roles(self) -> Mapping[str, Role]:
        raise NotImplementedError

    def router(self) -> APIRouter | None:
        return None

    def whoami_markdown(self) -> str:
        return ""
