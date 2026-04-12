from __future__ import annotations

from vossploee.capabilities.base import CapabilityModule, TaskWorker
from vossploee.capabilities.brainstormer.architect import BrainstormerArchitectWorker
from vossploee.capabilities.brainstormer.implementer import BrainstormerImplementerWorker
from vossploee.config import Settings


class BrainstormerCapability(CapabilityModule):
    name = "brainstormer"
    description = "Explores multiple ideas and solution directions for open-ended requests."

    def __init__(self, settings: Settings) -> None:
        self._architect_worker = BrainstormerArchitectWorker(settings)
        self._implementer_worker = BrainstormerImplementerWorker(settings)

    def get_architect_worker(self) -> TaskWorker:
        return self._architect_worker

    def get_implementer_worker(self) -> TaskWorker:
        return self._implementer_worker


def build_capability(settings: Settings) -> CapabilityModule:
    return BrainstormerCapability(settings)
