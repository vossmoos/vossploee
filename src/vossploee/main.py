from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Annotated, Any

import uvicorn
from fastapi import FastAPI, HTTPException, Query, Response, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from vossploee.capabilities.loader import load_capabilities
from vossploee.channels.loader import load_channels
from vossploee.config import Settings, get_settings
from vossploee.database import Database
from vossploee.memory.injector import MemoryInjector
from vossploee.middleware.reasoning import ReasoningRecorder
from vossploee.models import (
    ChannelInfo,
    CapabilityInfo,
    TaskTree,
)
from vossploee.repository import ChannelRepository, TaskRepository
from vossploee.whoami import read_markdown
from vossploee.workers import WorkerManager


class ApiKeyMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, *, expected_key: str) -> None:
        super().__init__(app)
        self.expected_key = expected_key

    async def dispatch(self, request: Request, call_next):
        expected = (self.expected_key or "").strip()
        if not expected:
            return await call_next(request)
        supplied = (request.headers.get("x-api-key") or "").strip()
        if not supplied:
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"detail": "Not authenticated"},
            )
        if supplied != self.expected_key:
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={"detail": "Forbidden"},
            )
        return await call_next(request)


@dataclass
class AppState:
    settings: Settings
    database: Database
    repository: TaskRepository
    channel_repo: ChannelRepository
    capabilities: dict[str, object]
    channels: dict[str, object]
    decomposer: object
    role_catalog: dict[str, object]
    memory_injector: MemoryInjector
    reasoning_recorder: ReasoningRecorder | None
    workers: WorkerManager


def create_app(settings: Settings | None = None) -> FastAPI:
    app_settings = settings or get_settings()
    database = Database(app_settings.database_path)
    repository = TaskRepository(database)
    channel_repo = ChannelRepository(database)
    app_whoami = read_markdown((__import__("pathlib").Path(__file__).resolve().parent / "WHOAMI.md"))
    capabilities = load_capabilities(app_settings)
    # Rebuild with whoami-aware constructors when supported.
    for cap_id in list(capabilities.keys()):
        mod = __import__(f"vossploee.capabilities.{cap_id}", fromlist=["build_capability"])
        build = getattr(mod, "build_capability")
        capabilities[cap_id] = build(app_settings, app_whoami=app_whoami)
    role_catalog: dict[str, object] = {}
    for cap in capabilities.values():
        for role in cap.roles().values():
            role_catalog[role.role_id] = role
    decomposer = role_catalog.get(app_settings.entrypoint_decomposer)
    if decomposer is None:
        raise RuntimeError(f"Entrypoint decomposer {app_settings.entrypoint_decomposer!r} is not loaded.")

    memory_injector = MemoryInjector(app_settings)
    reasoning = ReasoningRecorder(database) if app_settings.reasoning_log_enabled else None
    services = AppState(
        settings=app_settings,
        database=database,
        repository=repository,
        channel_repo=channel_repo,
        capabilities=capabilities,
        channels={},
        decomposer=decomposer,
        role_catalog=role_catalog,
        memory_injector=memory_injector,
        reasoning_recorder=reasoning,
        workers=None,  # type: ignore[arg-type]
    )
    channels = load_channels(app_settings, app_state=services)
    services.channels = channels
    workers = WorkerManager(
        settings=app_settings,
        repository=repository,
        role_catalog=role_catalog,
        role_context=__import__("vossploee.roles.base", fromlist=["RoleContext"]).RoleContext(
            repository=repository,
            channels=channels,
            tool_registry=__import__("vossploee.tools.registry", fromlist=["resolve_tools"]),
            settings=app_settings,
            memory_injector=memory_injector,
            reasoning_recorder=reasoning,
        ),
    )
    services.workers = workers

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        await database.initialize()
        for channel in channels.values():
            await channel.start()
        await workers.start()
        try:
            yield
        finally:
            await workers.stop()
            for channel in channels.values():
                await channel.stop()

    app = FastAPI(title=app_settings.app_name, lifespan=lifespan)
    app.add_middleware(ApiKeyMiddleware, expected_key=app_settings.api_key)
    app.state.services = services

    @app.get("/health")
    async def healthcheck() -> dict[str, str]:
        return {"status": "ok"}

    @app.get(f"{app_settings.api_prefix}/tasks", response_model=list[TaskTree])
    async def list_tasks() -> list[TaskTree]:
        return await app.state.services.repository.list_tree()

    @app.get(f"{app_settings.api_prefix}/log")
    async def list_log(
        offset: Annotated[int, Query(ge=0)] = 0,
        limit: Annotated[int, Query(ge=1, le=500)] = 10,
    ):
        return await app.state.services.repository.list_tasklog(offset=offset, limit=limit)

    @app.get(f"{app_settings.api_prefix}/capabilities", response_model=list[CapabilityInfo])
    async def list_capabilities() -> list[CapabilityInfo]:
        out: list[CapabilityInfo] = []
        for cap in app.state.services.capabilities.values():
            out.append(
                CapabilityInfo(
                    id=cap.id,
                    description=cap.description,
                    roles=sorted(role.role_id for role in cap.roles().values()),
                    tools=[],
                    whoami=cap.whoami_markdown(),
                )
            )
        return out

    @app.get(f"{app_settings.api_prefix}/channels", response_model=list[ChannelInfo])
    async def list_channels() -> list[ChannelInfo]:
        return [ChannelInfo(id=ch.id, description=ch.description) for ch in app.state.services.channels.values()]

    @app.delete(f"{app_settings.api_prefix}/tasks/{{task_id}}", status_code=status.HTTP_204_NO_CONTENT)
    async def delete_task(task_id: str) -> Response:
        deleted = await app.state.services.repository.delete_task_tree(task_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Task not found.")
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    for cap in capabilities.values():
        router = cap.router()
        if router:
            app.include_router(router, prefix=f"{app_settings.api_prefix}/{cap.id}")
    for ch in channels.values():
        router = ch.router()
        if router:
            app.include_router(router)

    return app


def __getattr__(name: str) -> Any:
    """Lazily build ``app`` so importing ``vossploee.main`` does not run ``get_settings()`` / load ``.env``."""
    if name == "app":
        return create_app()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def main() -> None:
    uvicorn.run(
        "vossploee.main:app",
        host="127.0.0.1",
        port=8000,
        reload=False,
    )
