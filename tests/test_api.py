from __future__ import annotations

import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from vossploee.capabilities import CapabilityConfigurationError
from vossploee.config import Settings
from vossploee.main import create_app


def _build_client(tmp_path: Path) -> TestClient:
    settings = Settings(
        database_path=tmp_path / "test-tasks.db",
        poll_interval_seconds=0.05,
        agent_model="test",
        enabled_capabilities=["consultant"],
    )
    app = create_app(settings)
    return TestClient(app)


def test_task_flow_builds_tree_and_deletes_descendants(tmp_path: Path) -> None:
    with _build_client(tmp_path) as client:
        response = client.post(
            "/api/tasks",
            json={
                "title": "Create agent scaffold",
                "description": (
                    "Accept user tasks. Split them into gherkin steps. "
                    "Run the implementation worker."
                ),
            },
        )

        assert response.status_code == 201
        root_task = response.json()
        assert root_task["queue_name"] == "queue01"
        assert root_task["agent_name"] == "Decomposer"
        assert root_task["capability_name"] == "consultant"

        deadline = time.time() + 3
        tree: list[dict] = []
        while time.time() < deadline:
            list_response = client.get("/api/tasks")
            assert list_response.status_code == 200
            tree = list_response.json()
            if tree and tree[0]["status"] == "completed" and tree[0]["children"]:
                if all(child["status"] == "completed" for child in tree[0]["children"]):
                    break
            time.sleep(0.05)

        assert len(tree) == 1
        assert tree[0]["id"] == root_task["id"]
        assert tree[0]["status"] == "completed"
        assert tree[0]["capability_name"] == "consultant"
        assert len(tree[0]["children"]) >= 1
        assert all(child["queue_name"] == "queue02" for child in tree[0]["children"])
        assert all(child["capability_name"] == "consultant" for child in tree[0]["children"])
        assert all(isinstance(child["gherkin"], str) and child["gherkin"] for child in tree[0]["children"])
        assert all(child["status"] == "completed" for child in tree[0]["children"])

        delete_response = client.delete(f"/api/tasks/{root_task['id']}")
        assert delete_response.status_code == 204

        list_response = client.get("/api/tasks")
        assert list_response.status_code == 200
        assert list_response.json() == []


def test_unknown_capability_is_rejected(tmp_path: Path) -> None:
    settings = Settings(
        database_path=tmp_path / "test-tasks.db",
        poll_interval_seconds=0.05,
        agent_model="test",
        enabled_capabilities=["missing-capability"],
    )

    with pytest.raises(CapabilityConfigurationError, match="Unknown capability id"):
        create_app(settings)


def test_capabilities_endpoint_returns_metadata(tmp_path: Path) -> None:
    settings = Settings(
        database_path=tmp_path / "test-tasks.db",
        poll_interval_seconds=0.05,
        agent_model="test",
        enabled_capabilities=["consultant", "brainstormer"],
    )
    app = create_app(settings)
    with TestClient(app) as client:
        response = client.get("/api/capabilities")
        assert response.status_code == 200
        payload = response.json()
        assert len(payload) == 2
        by_id = {item["id"]: item for item in payload}
        assert "consultant" in by_id and "brainstormer" in by_id
        assert by_id["consultant"]["title"]
        assert "Description" in by_id["consultant"]["readme_markdown"] or by_id["consultant"]["description"]
