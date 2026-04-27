from __future__ import annotations

from pathlib import Path

from vossploee.capabilities.base import CapabilityModule
from vossploee.capabilities.haiku.roles.writer import HaikuWriter


class HaikuCapability(CapabilityModule):
    id = "haiku"
    description = "Playful haiku writing capability."

    def __init__(self, app_whoami: str) -> None:
        whoami = self.whoami_markdown()
        self._roles = {"writer": HaikuWriter(app_whoami=app_whoami, capability_whoami=whoami)}

    def roles(self):
        return self._roles

    def whoami_markdown(self) -> str:
        path = Path(__file__).resolve().parent / "WHOAMI.md"
        if not path.exists():
            return "You are a playful haiku poet."
        return path.read_text(encoding="utf-8").strip()


def build_capability(settings, app_whoami: str = "") -> CapabilityModule:
    return HaikuCapability(app_whoami=app_whoami)
