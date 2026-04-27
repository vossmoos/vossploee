from __future__ import annotations

from vossploee.models import DecomposerVerdict, Message


async def dispatch_inbound(app_state, msg: Message) -> object:
    # Refinement resume path can be added here once message threading is wired from transport.
    plan = await app_state.decomposer.decompose(
        description=str(msg.body.get("text", "")),
        requester=msg.sender,
    )
    if plan.verdict == DecomposerVerdict.NOISE:
        return None
    if plan.verdict == DecomposerVerdict.REPLY:
        if msg.sender.channel_id in app_state.channels:
            await app_state.channels[msg.sender.channel_id].pushto(
                msg.sender,
                {
                    "kind": "reply",
                    "text": plan.reply_text or "",
                    "meta": {"in_reply_to": str(msg.id)},
                },
            )
        return {"reply_text": plan.reply_text}
    created = await app_state.repository.create_root_tasks(plan.roots)
    return created
