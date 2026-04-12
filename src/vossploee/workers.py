from __future__ import annotations

import asyncio
from contextlib import suppress

from vossploee.agents import AgentRegistry
from vossploee.capabilities import TaskWorker
from vossploee.config import Settings
from vossploee.repository import TaskRepository


class WorkerManager:
    def __init__(
        self,
        *,
        settings: Settings,
        repository: TaskRepository,
        agents: AgentRegistry,
    ) -> None:
        self.settings = settings
        self.repository = repository
        self.agents = agents
        self._tasks: list[asyncio.Task[None]] = []
        self._stop_event = asyncio.Event()

    async def start(self) -> None:
        self._stop_event.clear()
        self._tasks = [
            asyncio.create_task(
                self._queue_loop(capability_id, worker),
                name=f"{capability_id}-{worker.role_name.value.lower()}-worker",
            )
            for capability_id in sorted(self.agents.capabilities.keys())
            for worker in self.agents.capabilities[capability_id].get_workers()
        ]

    async def stop(self) -> None:
        self._stop_event.set()
        for task in self._tasks:
            task.cancel()
        for task in self._tasks:
            with suppress(asyncio.CancelledError):
                await task
        self._tasks.clear()

    async def _queue_loop(self, capability_id: str, worker: TaskWorker) -> None:
        while not self._stop_event.is_set():
            task = await self.repository.claim_next_task(
                queue_name=worker.queue_name,
                agent_name=worker.role_name,
                capability_name=capability_id,
            )
            if task is None:
                await asyncio.sleep(self.settings.poll_interval_seconds)
                continue

            try:
                await worker.handle(task=task, repository=self.repository)
            except Exception as exc:  # pragma: no cover - defensive worker safety
                await self.repository.fail_task(task.id, error_message=str(exc))
