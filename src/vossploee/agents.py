from __future__ import annotations

from pydantic_ai import Agent

from vossploee.capabilities import CapabilityModule
from vossploee.capabilities.loader import (
    decomposer_capability_catalog_text,
    list_capability_infos,
    load_capabilities,
)
from vossploee.agent_context import with_datetime_context
from vossploee.config import Settings
from vossploee.errors import AgentExecutionError
from vossploee.models import DecomposedPlan, DecomposedRootTask


class DecomposerAgentService:
    def __init__(self, settings: Settings) -> None:
        self.model_name = settings.agent_model
        self._max_roots = settings.max_decomposed_roots
        infos = list_capability_infos(settings)
        self._allowed_capability_ids = [info.id for info in infos]
        self._fallback_capability_id = self._allowed_capability_ids[0]
        catalog = decomposer_capability_catalog_text(infos)
        allowed = ", ".join(self._allowed_capability_ids)
        self.agent = Agent(
            model=self.model_name,
            output_type=DecomposedPlan,
            name="decomposer",
            system_prompt=(
                "You are the Decomposer agent. The user sends a single free-form natural-language "
                "request. You output `roots`: one or more queue01 root tasks.\n\n"
                "Default: use exactly ONE root with a concise `title`, clear `description`, and the "
                "best-matching `capability_name`. Omit `scheduled_at` so it runs as soon as possible.\n\n"
                "Recurring / scheduled monitoring (e.g. “check Upwork every hour for 24 hours”, "
                "“run this N times once per hour”): emit MULTIPLE roots with the SAME "
                "`capability_name` (usually `upworkmanager` for Upwork). Give each root a distinct "
                "`title` (e.g. include the run index or time). Each root's `description` should carry "
                "the same search/match criteria. Set `scheduled_at` for each root to the UTC instant "
                "when that run should start: typically consecutive hours from the current UTC time "
                "in the prompt context (e.g. run 1 at +1h, run 2 at +2h, …). Do not exceed the implied "
                f"number of runs (if the user asks for 24 hourly checks, emit 24 roots). "
                f"Never emit more than {self._max_roots} roots in one response.\n\n"
                "Valid capability ids (use the string exactly): "
                f"{allowed}.\n\n"
                "Capability reference:\n"
                f"{catalog}"
            ),
            defer_model_check=True,
        )

    def _normalize_plan(self, plan: DecomposedPlan) -> DecomposedPlan:
        if len(plan.roots) > self._max_roots:
            raise ValueError(
                f"Decomposer produced {len(plan.roots)} roots; maximum is {self._max_roots}."
            )
        fixed: list[DecomposedRootTask] = []
        for r in plan.roots:
            cap = (
                r.capability_name
                if r.capability_name in self._allowed_capability_ids
                else self._fallback_capability_id
            )
            fixed.append(r.model_copy(update={"capability_name": cap}))
        return DecomposedPlan(roots=fixed)

    async def decompose(self, *, description: str) -> DecomposedPlan:
        if not self.model_name:
            raise AgentExecutionError("Decomposer agent model is not configured.")

        result = await self.agent.run(
            with_datetime_context(
                "Normalize this natural-language request into queue01 root task(s).\n\n"
                f"User request:\n{description}"
            )
        )
        return self._normalize_plan(result.output)


class AgentRegistry:
    def __init__(self, settings: Settings) -> None:
        self.capabilities: dict[str, CapabilityModule] = load_capabilities(settings)
        self.decomposer = DecomposerAgentService(settings)
