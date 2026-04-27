from __future__ import annotations

from vossploee.capabilities.core.imap_tool import imap_send_mail
from vossploee.capabilities.core.memory_tools import memory_recall, memory_remember
from vossploee.tools.registry import register_tool


async def human_refine(question: str, user_id: str, channel_id: str = "email") -> str:
    return (
        "Use RoleOutcome.refine in role code for runtime HITL flow. "
        f"Received question={question!r}, user_id={user_id!r}, channel_id={channel_id!r}."
    )


def _register() -> None:
    register_tool(
        "core.imap",
        imap_send_mail,
        description="Send one email using configured SMTP settings.",
    )
    register_tool(
        "core.memory_remember",
        memory_remember,
        description="Store long-term memory text.",
    )
    register_tool(
        "core.memory_recall",
        memory_recall,
        description="Recall long-term memory text.",
    )
    register_tool(
        "core.human_refine",
        human_refine,
        description="Trigger a human refinement request.",
    )


_register()
