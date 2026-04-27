from __future__ import annotations

from pathlib import Path

from vossploee.capabilities.base import CapabilityModule
from vossploee.capabilities.uw.roles.executor import UwExecutor


class UwCapability(CapabilityModule):
    id = "uw"
    description = "Upwork sourcing capability."

    def __init__(self, app_whoami: str) -> None:
        whoami = self.whoami_markdown()
        self._roles = {"executor": UwExecutor(app_whoami=app_whoami, capability_whoami=whoami)}

    def roles(self):
        return self._roles

    def whoami_markdown(self) -> str:
        path = Path(__file__).resolve().parent / "WHOAMI.md"
        if not path.exists():
            return "You are a practical Upwork scouting specialist."
        return path.read_text(encoding="utf-8").strip()


def build_capability(settings, app_whoami: str = "") -> CapabilityModule:
    return UwCapability(app_whoami=app_whoami)
