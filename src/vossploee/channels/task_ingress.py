from __future__ import annotations

from dataclasses import dataclass

from vossploee.models import DecomposerVerdict, TaskRecord, UserRef


@dataclass(slots=True)
class IngressResult:
    verdict: DecomposerVerdict
    created: list[TaskRecord]
    reply_text: str | None


async def invoke_decomposer(*, app_state, description: str, requester: UserRef | None) -> IngressResult:
    plan = await app_state.decomposer.decompose(description=description, requester=requester)
    if plan.verdict == DecomposerVerdict.TASK:
        if requester is not None:
            for root in plan.roots:
                payload = dict(root.payload)
                payload.setdefault("requester", requester.model_dump())
                root.payload = payload
        created = await app_state.repository.create_root_tasks(plan.roots)
        return IngressResult(verdict=plan.verdict, created=created, reply_text=plan.reply_text)
    return IngressResult(verdict=plan.verdict, created=[], reply_text=plan.reply_text)
