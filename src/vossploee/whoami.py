from __future__ import annotations

from pathlib import Path


def read_markdown(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8").strip()


def compose_role_system_prompt(
    *,
    app_whoami: str,
    capability_whoami: str,
    role_prompt: str,
) -> str:
    chunks = [chunk.strip() for chunk in (app_whoami, capability_whoami, role_prompt) if chunk.strip()]
    return "\n\n".join(chunks)
