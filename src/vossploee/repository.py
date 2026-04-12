from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from vossploee.database import Database
from vossploee.models import AgentName, ArchitectTask, TaskKind, TaskQueue, TaskRecord, TaskStatus, TaskTree


class TaskRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    async def create_root_task(
        self,
        *,
        title: str,
        description: str,
        agent_name: AgentName,
        capability_name: str,
    ) -> TaskRecord:
        task_id = str(uuid4())
        now = self._now()

        async with self.database.connection() as conn:
            await conn.execute(
                """
                INSERT INTO tasks (
                    id, parent_id, root_id, title, description, queue_name, task_kind,
                    status, agent_name, capability_name, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task_id,
                    None,
                    task_id,
                    title,
                    description,
                    TaskQueue.QUEUE01,
                    TaskKind.BUSINESS,
                    TaskStatus.PENDING,
                    agent_name,
                    capability_name,
                    now,
                    now,
                ),
            )
            await conn.commit()

        created_task = await self.get_task(task_id)
        if created_task is None:  # pragma: no cover - defensive guard
            raise RuntimeError("Created root task could not be reloaded.")
        return created_task

    async def create_child_tasks(
        self,
        *,
        parent: TaskRecord,
        tasks: list[ArchitectTask],
    ) -> list[TaskRecord]:
        now = self._now()
        child_ids = [str(uuid4()) for _ in tasks]

        async with self.database.connection() as conn:
            for task_id, task in zip(child_ids, tasks, strict=True):
                await conn.execute(
                    """
                    INSERT INTO tasks (
                        id, parent_id, root_id, title, description, queue_name, task_kind,
                        status, agent_name, capability_name, gherkin, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        task_id,
                        parent.id,
                        parent.root_id,
                        task.title,
                        task.description,
                        TaskQueue.QUEUE02,
                        TaskKind.GHERKIN,
                        TaskStatus.PENDING,
                        AgentName.ARCHITECT,
                        parent.capability_name,
                        task.gherkin,
                        now,
                        now,
                    ),
                )
            await conn.commit()

        created_children: list[TaskRecord] = []
        for task_id in child_ids:
            child = await self.get_task(task_id)
            if child is None:  # pragma: no cover - defensive guard
                raise RuntimeError("Created child task could not be reloaded.")
            created_children.append(child)
        return created_children

    async def get_task(self, task_id: str) -> TaskRecord | None:
        async with self.database.connection() as conn:
            cursor = await conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
            row = await cursor.fetchone()

        return self._to_record(row) if row else None

    async def list_flat(self) -> list[TaskRecord]:
        async with self.database.connection() as conn:
            cursor = await conn.execute(
                "SELECT * FROM tasks ORDER BY created_at ASC, id ASC"
            )
            rows = await cursor.fetchall()

        return [self._to_record(row) for row in rows]

    async def list_tree(self) -> list[TaskTree]:
        items = await self.list_flat()
        nodes = {
            item.id: TaskTree(**item.model_dump(), children=[])
            for item in items
        }

        roots: list[TaskTree] = []
        for item in items:
            node = nodes[item.id]
            if item.parent_id and item.parent_id in nodes:
                nodes[item.parent_id].children.append(node)
            else:
                roots.append(node)

        return roots

    async def delete_task_tree(self, task_id: str) -> bool:
        async with self.database.connection() as conn:
            cursor = await conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
            await conn.commit()
            return cursor.rowcount > 0

    async def claim_next_task(
        self,
        *,
        queue_name: TaskQueue,
        agent_name: AgentName,
        capability_name: str,
    ) -> TaskRecord | None:
        now = self._now()

        async with self.database.connection() as conn:
            await conn.execute("BEGIN IMMEDIATE")
            cursor = await conn.execute(
                """
                SELECT id
                FROM tasks
                WHERE queue_name = ? AND status = ? AND capability_name = ?
                ORDER BY created_at ASC, id ASC
                LIMIT 1
                """,
                (queue_name, TaskStatus.PENDING, capability_name),
            )
            row = await cursor.fetchone()

            if row is None:
                await conn.rollback()
                return None

            await conn.execute(
                """
                UPDATE tasks
                SET status = ?, agent_name = ?, claimed_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (TaskStatus.IN_PROGRESS, agent_name, now, now, row["id"]),
            )
            cursor = await conn.execute("SELECT * FROM tasks WHERE id = ?", (row["id"],))
            claimed_row = await cursor.fetchone()
            await conn.commit()

        return self._to_record(claimed_row) if claimed_row else None

    async def complete_task(self, task_id: str, *, result: str) -> None:
        now = self._now()
        async with self.database.connection() as conn:
            await conn.execute(
                """
                UPDATE tasks
                SET status = ?, result = ?, completed_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (TaskStatus.COMPLETED, result, now, now, task_id),
            )
            await conn.commit()

    async def fail_task(self, task_id: str, *, error_message: str) -> None:
        now = self._now()
        async with self.database.connection() as conn:
            await conn.execute(
                """
                UPDATE tasks
                SET status = ?, result = ?, updated_at = ?
                WHERE id = ?
                """,
                (TaskStatus.FAILED, error_message, now, task_id),
            )
            await conn.commit()

    @staticmethod
    def _to_record(row: object) -> TaskRecord:
        return TaskRecord.model_validate(dict(row))

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat()
