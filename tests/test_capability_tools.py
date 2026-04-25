from __future__ import annotations

import importlib.util
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import pytest

from vossploee.capabilities.capability_settings import CapabilitySettings
from vossploee.capabilities.capability_settings import load_capability_settings
from vossploee.capabilities.loader import bootstrap_tool_registry, load_capabilities
from vossploee.config import Settings
from vossploee.errors import CapabilityConfigurationError
from vossploee.tools.registry import is_registered, register_tool


def test_core_imap_registers_after_bootstrap() -> None:
    bootstrap_tool_registry()
    assert is_registered("core.imap")
    assert is_registered("core.queue_list_all")
    assert is_registered("core.queue_delete_batch_resolved")
    assert is_registered("core.memory_remember")
    assert is_registered("core.memory_recall")
    assert is_registered("newsroom.news_monitor")
    assert is_registered("newsroom.news_read")
    assert is_registered("newsroom.news_translate")
    if importlib.util.find_spec("vossploee.capabilities.upworkmanager") is not None:
        assert is_registered("upworkmanager.search_jobs")


def test_duplicate_registration_raises() -> None:
    async def _dummy() -> str:
        return "x"

    qid = f"core._dup_{uuid4().hex}"
    register_tool(qid, _dummy)
    with pytest.raises(ValueError, match="already registered"):
        register_tool(qid, _dummy)


def test_unknown_tool_in_capability_config_fails_startup(tmp_path: Path) -> None:
    settings = Settings(
        database_path=tmp_path / "t.db",
        poll_interval_seconds=0.05,
        agent_model="test",
        enabled_capabilities=["core"],
        openai_api_key="",
    )

    bad = CapabilitySettings("core", None, ("not.registered.tool",))

    def _load(cid: str) -> CapabilitySettings:
        if cid == "core":
            return bad
        raise AssertionError

    with (
        patch("vossploee.capabilities.loader.load_capability_settings", side_effect=_load),
        pytest.raises(CapabilityConfigurationError, match="unknown tool"),
    ):
        load_capabilities(settings)


def test_upworkmanager_settings_defaults_are_available() -> None:
    pytest.importorskip("vossploee.capabilities.upworkmanager", reason="optional capability package")
    cfg = load_capability_settings("upworkmanager")
    assert cfg.upwork is not None
    assert cfg.upwork.api_key_env == "VOSSPLOEE_UPWORK_API_KEY"
    assert cfg.architect_prompt is not None
    assert 1 <= cfg.upwork.search_defaults.minutes <= 1440
    assert 1 <= cfg.upwork.search_defaults.limit <= 50
    assert "core.memory_remember" in cfg.tools
    assert "core.memory_recall" in cfg.tools
