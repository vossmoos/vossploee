from __future__ import annotations

import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from vossploee.capabilities import CapabilityConfigurationError
from vossploee.config import Settings, get_settings
from vossploee.main import create_app

_TEST_API_KEY = "test-x-api-key"
# Role-specific defaults in Settings otherwise still point at real provider ids.
_TEST_MODELS = {
    "agent_model": "test",
    "decomposer_model": "test",
    "architect_model": "test",
    "implementer_model": "test",
}


@pytest.fixture(autouse=True)
def _isolate_openai_env_for_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Project ``.env`` can set OPENAI_API_KEY; isolate so memory tools do not call OpenAI in tests."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("VOSSPLOEE_OPENAI_API_KEY", raising=False)
    get_settings.cache_clear()


def _build_client(tmp_path: Path) -> TestClient:
    settings = Settings(
        database_path=tmp_path / "test-tasks.db",
        chroma_path=tmp_path / "chroma",
        poll_interval_seconds=0.05,
        enabled_capabilities=["core"],
        api_key=_TEST_API_KEY,
        **_TEST_MODELS,
    )
    app = create_app(settings)
    return TestClient(app, headers={"X-API-KEY": _TEST_API_KEY})


def test_task_flow_archives_finished_tree_to_tasklog(tmp_path: Path) -> None:
    with _build_client(tmp_path) as client:
        response = client.post(
            "/api/tasks",
            json={
                "description": (
                    "Create agent scaffold: accept user tasks, split them into gherkin steps, "
                    "run the implementation worker."
                ),
            },
        )

        assert response.status_code == 201
        roots = response.json()
        assert isinstance(roots, list)
        assert len(roots) >= 1
        root_task = roots[0]
        assert root_task["queue_name"] == "queue01"
        assert root_task["agent_name"] == "Decomposer"
        assert root_task["capability_name"] == "core"

        # Allow time for first Chroma embedding model download on cold machines.
        deadline = time.time() + 120
        log_entries: list[dict] = []
        while time.time() < deadline:
            log_response = client.get("/api/tasklog")
            assert log_response.status_code == 200
            log_entries = log_response.json()
            if len(log_entries) >= 1:
                break
            time.sleep(0.05)

        assert len(log_entries) == 1
        entry = log_entries[0]
        assert entry["root_id"] == root_task["id"]
        assert entry["capability_name"] == "core"
        payload = entry["payload"]
        assert payload["id"] == root_task["id"]
        assert payload["status"] == "completed"
        assert payload["queue_name"] == "queue01"
        assert len(payload["children"]) >= 1
        assert all(child["queue_name"] == "queue02" for child in payload["children"])
        assert all(child["capability_name"] == "core" for child in payload["children"])
        assert all(isinstance(child["gherkin"], str) and child["gherkin"] for child in payload["children"])
        assert all(child["status"] == "completed" for child in payload["children"])

        page = client.get("/api/log")
        assert page.status_code == 200
        assert len(page.json()) == 1
        assert page.json()[0]["root_id"] == root_task["id"]

        page2 = client.get("/api/log", params={"offset": 1, "limit": 10})
        assert page2.status_code == 200
        assert page2.json() == []

        list_response = client.get("/api/tasks")
        assert list_response.status_code == 200
        assert list_response.json() == []


def test_log_empty_database_defaults(tmp_path: Path) -> None:
    with _build_client(tmp_path) as client:
        r = client.get("/api/log")
        assert r.status_code == 200
        assert r.json() == []


def test_api_key_missing_returns_401(tmp_path: Path) -> None:
    settings = Settings(
        database_path=tmp_path / "test-tasks.db",
        poll_interval_seconds=0.05,
        enabled_capabilities=["core"],
        api_key=_TEST_API_KEY,
        **_TEST_MODELS,
    )
    app = create_app(settings)
    with TestClient(app) as client:
        r = client.get("/health")
        assert r.status_code == 401
        assert r.json()["detail"] == "Not authenticated"


def test_api_key_empty_skips_http_key_check(tmp_path: Path) -> None:
    settings = Settings(
        database_path=tmp_path / "test-tasks.db",
        poll_interval_seconds=0.05,
        enabled_capabilities=["core"],
        api_key="",
        **_TEST_MODELS,
    )
    app = create_app(settings)
    with TestClient(app) as client:
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json() == {"status": "ok"}


def test_api_key_wrong_returns_403(tmp_path: Path) -> None:
    settings = Settings(
        database_path=tmp_path / "test-tasks.db",
        poll_interval_seconds=0.05,
        enabled_capabilities=["core"],
        api_key=_TEST_API_KEY,
        **_TEST_MODELS,
    )
    app = create_app(settings)
    with TestClient(app) as client:
        r = client.get("/health", headers={"X-API-KEY": "wrong"})
        assert r.status_code == 403
        assert r.json()["detail"] == "Forbidden"


def test_unknown_capability_is_rejected(tmp_path: Path) -> None:
    settings = Settings(
        database_path=tmp_path / "test-tasks.db",
        poll_interval_seconds=0.05,
        enabled_capabilities=["missing-capability"],
        **_TEST_MODELS,
    )

    with pytest.raises(CapabilityConfigurationError, match="Unknown capability id"):
        create_app(settings)


def test_capabilities_endpoint_returns_metadata(tmp_path: Path) -> None:
    settings = Settings(
        database_path=tmp_path / "test-tasks.db",
        chroma_path=tmp_path / "chroma",
        poll_interval_seconds=0.05,
        enabled_capabilities=["core", "brainstormer"],
        api_key=_TEST_API_KEY,
        **_TEST_MODELS,
    )
    app = create_app(settings)
    with TestClient(app, headers={"X-API-KEY": _TEST_API_KEY}) as client:
        response = client.get("/api/capabilities")
        assert response.status_code == 200
        payload = response.json()
        assert len(payload) == 2
        by_id = {item["id"]: item for item in payload}
        assert "core" in by_id and "brainstormer" in by_id
        assert by_id["core"]["title"]
        assert "Description" in by_id["core"]["readme_markdown"] or by_id["core"]["description"]
        assert by_id["core"]["tools"] == [
            "core.imap",
            "core.queue_delete",
            "core.queue_delete_batch",
            "core.queue_delete_batch_resolved",
            "core.queue_defer",
            "core.memory_remember",
            "core.memory_recall",
        ]
        assert by_id["brainstormer"]["tools"] == ["core.memory_remember", "core.memory_recall"]
