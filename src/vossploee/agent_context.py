from __future__ import annotations

from datetime import UTC, datetime


def format_agent_datetime_context() -> str:
    """Short prefix injected into agent prompts so models can reason about current time."""
    now = datetime.now(UTC)
    return (
        "Current date and time (UTC only, ISO 8601):\n"
        f"- {now.isoformat(timespec='seconds')}\n"
        f"- Date only (UTC): {now.date().isoformat()}\n"
        "- Rule: interpret and output all timestamps in UTC. Convert any local timezone time to UTC before using it."
    )


def with_datetime_context(prompt: str) -> str:
    """Prepend UTC date/time context to a user or task prompt."""
    return f"{format_agent_datetime_context()}\n\n{prompt}"
