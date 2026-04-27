from __future__ import annotations

import asyncio
from contextlib import suppress
from datetime import UTC, datetime

from vossploee.config import Settings
from vossploee.models import UserRef
from vossploee.repository import TaskRepository
from vossploee.roles.base import RoleContext


class WorkerManager:
    def __init__(
        self,
        *,
        settings: Settings,
        repository: TaskRepository,
        role_catalog: dict[str, object],
        role_context: RoleContext,
    ) -> None:
        self.settings = settings
        self.repository = repository
        self.role_catalog = role_catalog
        self.role_context = role_context
        self._tasks: list[asyncio.Task[None]] = []
        self._stop_event = asyncio.Event()

    async def start(self) -> None:
        self._stop_event.clear()
        self._tasks = [asyncio.create_task(self._queue_loop(role_id), name=f"{role_id}-worker") for role_id in sorted(self.role_catalog)]

    async def stop(self) -> None:
        self._stop_event.set()
        for task in self._tasks:
            task.cancel()
        for task in self._tasks:
            with suppress(asyncio.CancelledError):
                await task
        self._tasks.clear()

    async def _queue_loop(self, role_id: str) -> None:
        role = self.role_catalog[role_id]
        while not self._stop_event.is_set():
            task = await self.repository.claim_next_task(
                role_id=role_id,
                now=datetime.now(UTC),
            )
            if task is None:
                await asyncio.sleep(self.settings.poll_interval_seconds)
                continue

            try:
                outcome = await role.handle(task, self.role_context)
                if outcome.kind == "completed":
                    await self.repository.complete_task(str(task.id), result=outcome.artifact or outcome.summary or "")
                    await self._notify_requester(task=task, text=outcome.summary or "Task completed.", task_id=str(task.id))
                elif outcome.kind == "failed":
                    await self.repository.fail_task(str(task.id), error_message=outcome.error or "Role failed")
                    await self._notify_requester(
                        task=task,
                        text=f"Task failed: {outcome.error or 'Role failed'}",
                        task_id=str(task.id),
                    )
                elif outcome.kind == "spawn":
                    await self.repository.create_child_tasks(parent=task, tasks=outcome.children)
                    await self.repository.complete_task(str(task.id), result=outcome.summary or "Spawned child tasks")
                    await self._notify_requester(
                        task=task,
                        text=outcome.summary or f"Task spawned {len(outcome.children)} child task(s).",
                        task_id=str(task.id),
                    )
                elif outcome.kind == "defer" and outcome.until is not None:
                    task_payload = dict(task.payload)
                    task_payload["defer_until"] = outcome.until.isoformat()
                    await self.repository.fail_task(str(task.id), error_message="Deferral outcome is not yet persisted in this build.")
                elif outcome.kind == "refine" and outcome.user and outcome.question:
                    await self.repository.set_refining(task_id=str(task.id), user=outcome.user)
                    channel = self.role_context.channels.get(outcome.user.channel_id)
                    if channel is None:
                        await self.repository.fail_task(str(task.id), error_message="Channel missing for refine request.")
                    else:
                        await channel.pushto(outcome.user, outcome.question, task_id=str(task.id))
                else:
                    await self.repository.fail_task(str(task.id), error_message=f"Unknown outcome kind: {outcome.kind}")
            except Exception as exc:  # pragma: no cover - defensive worker safety
                await self.repository.fail_task(str(task.id), error_message=str(exc))
                await self._notify_requester(task=task, text=f"Task failed: {exc}", task_id=str(task.id))

    async def _notify_requester(self, *, task, text: str, task_id: str) -> None:
        requester_raw = task.payload.get("requester")
        if not requester_raw:
            return
        try:
            requester = UserRef.model_validate(requester_raw)
        except Exception:
            return
        channel = self.role_context.channels.get(requester.channel_id)
        if channel is None:
            return
        await channel.pushto(
            requester,
            {"kind": "task_update", "text": text, "meta": {"task_id": task_id}},
            task_id=task_id,
        )
