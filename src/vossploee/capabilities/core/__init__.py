from __future__ import annotations

from pathlib import Path

from vossploee.capabilities.base import CapabilityModule
from vossploee.capabilities.core.roles.decomposer import CoreDecomposer
from vossploee.capabilities.core.roles.executor import CoreExecutor


class CoreCapability(CapabilityModule):
    id = "core"
    description = "Core orchestration capability."

    def __init__(self, settings, app_whoami: str) -> None:
        whoami = self.whoami_markdown()
        self._roles = {
            "decomposer": CoreDecomposer(app_whoami=app_whoami, capability_whoami=whoami),
            "executor": CoreExecutor(app_whoami=app_whoami, capability_whoami=whoami),
        }

    def roles(self):
        return self._roles

    def whoami_markdown(self) -> str:
        path = Path(__file__).resolve().parent / "WHOAMI.md"
        if not path.exists():
            return "You are the core capability."
        return path.read_text(encoding="utf-8").strip()


def build_capability(settings, app_whoami: str = "") -> CapabilityModule:
    return CoreCapability(settings, app_whoami=app_whoami)
