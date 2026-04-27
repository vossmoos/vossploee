from __future__ import annotations

from vossploee.capabilities.uw.upwork_api_tool import search_recent_upwork_jobs
from vossploee.tools.registry import register_tool


def _register() -> None:
    register_tool(
        "uw.search_jobs",
        search_recent_upwork_jobs,
        description="Search recent Upwork jobs via GraphQL API.",
    )


_register()
