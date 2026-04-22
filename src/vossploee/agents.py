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
from vossploee.models import AgentName, DecomposedPlan, DecomposedRootTask, TaskQueuePolicy
from vossploee.task_queue_intent import decomposer_root_should_use_lifo


class DecomposerAgentService:
    def __init__(self, settings: Settings) -> None:
        self.model_name = settings.model_for_agent(AgentName.DECOMPOSER)
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
                "Multiple roots: if the request genuinely needs **different** kinds of work, emit **one "
                "or more** queue01 roots—either several under the **same** capability (e.g. scheduled "
                "monitoring runs) or roots assigned to **different** capabilities when the user’s ask "
                "clearly combines unrelated domains. Each root is independent input for that capability’s "
                "Architect later.\n\n"
                "Long-term memory across roots: enabled capabilities may expose semantic memory tools to "
                "their Architect / Implementer agents. Memory is **scoped per capability**—two different "
                "`capability_name` values do not share the same store. When the user’s ask fits a **chain** "
                "of work (e.g. one phase should leave durable notes, a later phase should use those notes "
                "for an outcome such as outbound mail, a report, or a decision), you may plan **multiple** "
                "queue01 roots, usually under the **same** capability so later agents can recall what "
                "earlier agents stored. Make each root’s `title`/`description` explicit about that root’s "
                "role in the chain; if order matters beyond normal queue ordering, say so and set "
                "`scheduled_at` on later roots when they must wait for time, not only for fifo/lifo. "
                "Downstream agents decide **when** to call remember/recall; you only split the user’s "
                "intent into roots they can run.\n\n"
                "Choosing `capability_name`: reason about **intent**, not keyword matching. Domain work "
                "(e.g. search Upwork, draft applies, brainstorm product ideas) belongs to the matching "
                "domain capability (`upworkmanager`, `brainstormer`, …). **Meta-requests about the task "
                "system itself**—cancel/remove/prune queued work that belongs to **another** "
                "capability, clear a scheduler of foreign jobs, or operate on the queue as "
                "infrastructure—belong to **`core`**. In the root `title`/`description`, state the target "
                "explicitly (e.g. which capability’s queue01 roots to remove, date filters, “all "
                "upworkmanager monitors”). Example: “Remove all Upwork tasks from the scheduler” → "
                "**one** `core` root whose description says to remove all pending queue01 roots where "
                "the work is for `upworkmanager` (not an `upworkmanager` root—that would run the "
                "Upwork Architect instead of platform cleanup).\n\n"
                "Queue policy (`queue_policy`, default `fifo`): workers use it when claiming queue01 "
                "roots: pending `lifo` roots run before any pending `fifo` root; among `lifo`, newest "
                "first; among `fifo`, oldest first. Set `queue_policy` to `lifo` when this root must be "
                "processed **before** older fifo work (e.g. urgent cancel/clear-queue style requests).\n\n"
                "Recurring / scheduled monitoring (e.g. “check Upwork every hour for 24 hours”, "
                "“run this N times once per hour”): emit MULTIPLE roots with the SAME "
                "`capability_name` (usually `upworkmanager` for Upwork). Give each root a distinct "
                "`title` (e.g. include the run index or time). Each root's `description` should carry "
                "the same search/match criteria. Set `scheduled_at` for each root to the UTC instant "
                "when that run should start: typically consecutive hours from the current UTC time "
                "in the prompt context (e.g. run 1 at +1h, run 2 at +2h, …). Do not exceed the implied "
                f"number of runs (if the user asks for 24 hourly checks, emit 24 roots). "
                "Do not invent a narrow time window in the root description (for example, "
                "'last 10 minutes') unless the user explicitly asked for that value. For recurring "
                "cadence requests, either omit explicit minutes in the root text or use a window that "
                "is at least the cadence interval to avoid coverage gaps if it is needed for the user. "
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
            updates: dict[str, object] = {"capability_name": cap}
            if decomposer_root_should_use_lifo(r.title, r.description):
                updates["queue_policy"] = TaskQueuePolicy.LIFO
            fixed.append(r.model_copy(update=updates))
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
