from __future__ import annotations

from vossploee.capabilities.base import CapabilityModule, TaskWorker
from vossploee.capabilities.core.architect import CoreArchitectWorker
from vossploee.capabilities.core.implementer import CoreImplementerWorker
from vossploee.config import Settings


class CoreCapability(CapabilityModule):
    name = "core"
    description = (
        "Default capability: Planner breaks business asks into doable actions; Implementer executes "
        "them (tools, email, drafts, checks—not only code). Baseline tools in config.toml."
    )

    def __init__(self, settings: Settings) -> None:
        self._architect_worker = CoreArchitectWorker(settings)
        self._implementer_worker = CoreImplementerWorker(settings)

    def get_architect_worker(self) -> TaskWorker:
        return self._architect_worker

    def get_implementer_worker(self) -> TaskWorker:
        return self._implementer_worker


def build_capability(settings: Settings) -> CapabilityModule:
    return CoreCapability(settings)
