from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass

import uvicorn
from fastapi import FastAPI, HTTPException, Response, status

from vossploee.agents import AgentRegistry
from vossploee.config import Settings, get_settings
from vossploee.database import Database
from vossploee.capabilities.loader import list_capability_infos
from vossploee.models import AgentName, CapabilityInfo, CreateTaskRequest, TaskRecord, TaskTree
from vossploee.repository import TaskRepository
from vossploee.workers import WorkerManager


@dataclass
class AppState:
    settings: Settings
    database: Database
    repository: TaskRepository
    agents: AgentRegistry
    workers: WorkerManager


def create_app(settings: Settings | None = None) -> FastAPI:
    app_settings = settings or get_settings()
    database = Database(app_settings.database_path)
    repository = TaskRepository(database)
    agents = AgentRegistry(app_settings)
    workers = WorkerManager(
        settings=app_settings,
        repository=repository,
        agents=agents,
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        await database.initialize()
        await workers.start()
        try:
            yield
        finally:
            await workers.stop()

    app = FastAPI(title=app_settings.app_name, lifespan=lifespan)
    app.state.services = AppState(
        settings=app_settings,
        database=database,
        repository=repository,
        agents=agents,
        workers=workers,
    )

    @app.get("/health")
    async def healthcheck() -> dict[str, str]:
        return {"status": "ok"}

    @app.post(
        f"{app_settings.api_prefix}/tasks",
        response_model=TaskRecord,
        status_code=status.HTTP_201_CREATED,
    )
    async def create_task(payload: CreateTaskRequest) -> TaskRecord:
        normalized = await app.state.services.agents.decomposer.decompose(
            title=payload.title,
            description=payload.description,
        )
        task = await app.state.services.repository.create_root_task(
            title=normalized.title,
            description=normalized.description,
            agent_name=AgentName.DECOMPOSER,
            capability_name=normalized.capability_name,
        )
        if task is None:  # pragma: no cover - defensive fallback
            raise HTTPException(status_code=500, detail="Task creation failed.")
        return task

    @app.get(f"{app_settings.api_prefix}/tasks", response_model=list[TaskTree])
    async def list_tasks() -> list[TaskTree]:
        return await app.state.services.repository.list_tree()

    @app.get(f"{app_settings.api_prefix}/capabilities", response_model=list[CapabilityInfo])
    async def list_capabilities() -> list[CapabilityInfo]:
        return list_capability_infos(app.state.services.settings)

    @app.delete(f"{app_settings.api_prefix}/tasks/{{task_id}}", status_code=status.HTTP_204_NO_CONTENT)
    async def delete_task(task_id: str) -> Response:
        deleted = await app.state.services.repository.delete_task_tree(task_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Task not found.")
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    return app


app = create_app()


def main() -> None:
    uvicorn.run(
        "vossploee.main:app",
        host="127.0.0.1",
        port=8000,
        reload=False,
    )
