from __future__ import annotations

from vossploee.capabilities.base import CapabilityModule, TaskWorker
from vossploee.capabilities.consultant.architect import ConsultantArchitectWorker
from vossploee.capabilities.consultant.implementer import ConsultantImplementerWorker
from vossploee.config import Settings


class ConsultantCapability(CapabilityModule):
    name = "consultant"
    description = "Default capability with no extra tools or custom execution modules."

    def __init__(self, settings: Settings) -> None:
        self._architect_worker = ConsultantArchitectWorker(settings)
        self._implementer_worker = ConsultantImplementerWorker(settings)

    def get_architect_worker(self) -> TaskWorker:
        return self._architect_worker

    def get_implementer_worker(self) -> TaskWorker:
        return self._implementer_worker


def build_capability(settings: Settings) -> CapabilityModule:
    return ConsultantCapability(settings)
