from __future__ import annotations

from pydantic_ai import Agent

from vossploee.capabilities import CapabilityModule
from vossploee.capabilities.loader import (
    decomposer_capability_catalog_text,
    list_capability_infos,
    load_capabilities,
)
from vossploee.config import Settings
from vossploee.errors import AgentExecutionError
from vossploee.models import DecomposedTask


class DecomposerAgentService:
    def __init__(self, settings: Settings) -> None:
        self.model_name = settings.agent_model
        infos = list_capability_infos(settings)
        self._allowed_capability_ids = [info.id for info in infos]
        self._fallback_capability_id = self._allowed_capability_ids[0]
        catalog = decomposer_capability_catalog_text(infos)
        allowed = ", ".join(self._allowed_capability_ids)
        self.agent = Agent(
            model=self.model_name,
            output_type=DecomposedTask,
            name="decomposer",
            system_prompt=(
                "You are the Decomposer agent. Normalize a business request into a concise "
                "title and a clean description suitable for queue01. "
                "You must choose exactly ONE capability for downstream processing: set "
                "`capability_name` to the capability id that best matches the user's intent. "
                f"Valid ids (use the string exactly): {allowed}.\n\n"
                "Capability reference:\n"
                f"{catalog}"
            ),
            defer_model_check=True,
        )

    async def decompose(self, *, title: str, description: str) -> DecomposedTask:
        if not self.model_name:
            raise AgentExecutionError("Decomposer agent model is not configured.")

        result = await self.agent.run(
            "Normalize this business request and assign the best capability.\n"
            f"Title: {title}\n"
            f"Description: {description}"
        )
        output = result.output
        if output.capability_name not in self._allowed_capability_ids:
            output = output.model_copy(update={"capability_name": self._fallback_capability_id})
        return output


class AgentRegistry:
    def __init__(self, settings: Settings) -> None:
        self.capabilities: dict[str, CapabilityModule] = load_capabilities(settings)
        self.decomposer = DecomposerAgentService(settings)
