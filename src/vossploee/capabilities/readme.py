from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ParsedCapabilityReadme:
    title: str
    description: str
    functionality: str
    raw_markdown: str


def read_capability_readme_text(capability_id: str) -> str:
    """Load README.md from vossploee/capabilities/<id>/README.md (works in src and wheel layouts)."""
    pkg = import_module("vossploee.capabilities")
    base = Path(next(iter(pkg.__path__)))
    path = base / capability_id / "README.md"
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8")


def parse_capability_readme(markdown: str, capability_id: str) -> ParsedCapabilityReadme:
    text = markdown.strip()
    if not text:
        return ParsedCapabilityReadme(
            title=capability_id,
            description="",
            functionality="",
            raw_markdown="",
        )

    lines = text.splitlines()
    title = capability_id
    body_lines: list[str]
    if lines and lines[0].startswith("#"):
        title = lines[0].lstrip("#").strip()
        body_lines = lines[1:]
    else:
        body_lines = lines[:]

    sections: dict[str, list[str]] = {}
    current_key: str | None = None
    buf: list[str] = []

    def flush_current() -> None:
        nonlocal buf
        if not buf:
            return
        if current_key is None:
            sections.setdefault("_preamble", []).extend(buf)
        else:
            sections[current_key] = buf[:]
        buf = []

    for line in body_lines:
        if line.startswith("##"):
            flush_current()
            header = line[2:].strip().lower()
            current_key = header.split()[0] if header else None
            buf = []
        else:
            buf.append(line)
    flush_current()

    desc = "\n".join(sections.get("description", [])).strip()
    func = "\n".join(sections.get("functionality", [])).strip()

    if not desc and not func:
        preamble = "\n".join(sections.get("_preamble", [])).strip()
        body = preamble or "\n".join(body_lines).strip()
        paras = [p.strip() for p in body.split("\n\n") if p.strip()]
        if paras:
            desc = paras[0]
            func = "\n\n".join(paras[1:]) if len(paras) > 1 else ""

    return ParsedCapabilityReadme(
        title=title,
        description=desc,
        functionality=func,
        raw_markdown=text,
    )
