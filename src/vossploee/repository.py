from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import uuid4

from vossploee.database import Database
from vossploee.models import (
    AgentName,
    ArchitectTask,
    TaskKind,
    TaskLogEntry,
    TaskQueue,
    TaskQueuePolicy,
    TaskRecord,
    TaskStatus,
    TaskTree,
)


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
        scheduled_at: datetime | None = None,
        queue_policy: TaskQueuePolicy = TaskQueuePolicy.FIFO,
    ) -> TaskRecord:
        task_id = str(uuid4())
        now = self._now()
        sched = self._dt_to_iso(scheduled_at)

        async with self.database.connection() as conn:
            await conn.execute(
                """
                INSERT INTO tasks (
                    id, parent_id, root_id, title, description, queue_name, task_kind,
                    status, agent_name, capability_name, created_at, updated_at, scheduled_at,
                    queue_policy
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    sched,
                    queue_policy.value,
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
                sched = self._dt_to_iso(task.scheduled_at)
                await conn.execute(
                    """
                    INSERT INTO tasks (
                        id, parent_id, root_id, title, description, queue_name, task_kind,
                        status, agent_name, capability_name, gherkin, created_at, updated_at,
                        scheduled_at, queue_policy
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                        sched,
                        task.queue_policy.value,
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

    async def list_queue01_tasks(
        self,
        *,
        capability_name: str,
        search: str | None = None,
    ) -> list[TaskRecord]:
        async with self.database.connection() as conn:
            if search and search.strip():
                like = f"%{search.strip()}%"
                cursor = await conn.execute(
                    """
                    SELECT * FROM tasks
                    WHERE queue_name = ? AND capability_name = ?
                      AND (title LIKE ? OR description LIKE ?)
                    ORDER BY created_at ASC, id ASC
                    """,
                    (TaskQueue.QUEUE01, capability_name, like, like),
                )
            else:
                cursor = await conn.execute(
                    """
                    SELECT * FROM tasks
                    WHERE queue_name = ? AND capability_name = ?
                    ORDER BY created_at ASC, id ASC
                    """,
                    (TaskQueue.QUEUE01, capability_name),
                )
            rows = await cursor.fetchall()

        return [self._to_record(row) for row in rows]

    async def list_queue01_tasks_all_capabilities(
        self,
        *,
        search: str | None = None,
    ) -> list[TaskRecord]:
        """All queue01 roots across capabilities (for platform / core orchestration)."""
        async with self.database.connection() as conn:
            if search and search.strip():
                like = f"%{search.strip()}%"
                cursor = await conn.execute(
                    """
                    SELECT * FROM tasks
                    WHERE queue_name = ?
                      AND (title LIKE ? OR description LIKE ?)
                    ORDER BY capability_name ASC, created_at ASC, id ASC
                    """,
                    (TaskQueue.QUEUE01, like, like),
                )
            else:
                cursor = await conn.execute(
                    """
                    SELECT * FROM tasks
                    WHERE queue_name = ?
                    ORDER BY capability_name ASC, created_at ASC, id ASC
                    """,
                    (TaskQueue.QUEUE01,),
                )
            rows = await cursor.fetchall()

        return [self._to_record(row) for row in rows]

    async def delete_queue01_roots_by_ids(
        self,
        *,
        task_ids: list[str],
    ) -> tuple[int, list[str]]:
        """Delete queue01 roots by id regardless of capability (each row's subtree removed)."""
        messages: list[str] = []
        ok_n = 0
        seen: set[str] = set()
        for raw in task_ids:
            tid = (raw or "").strip()
            if not tid or tid in seen:
                continue
            seen.add(tid)
            task = await self.get_task(tid)
            if task is None:
                messages.append(f"{tid!r}: not found.")
                continue
            if task.queue_name != TaskQueue.QUEUE01:
                messages.append(f"{tid!r}: not a queue01 root.")
                continue
            deleted = await self.delete_task_tree(tid)
            if deleted:
                ok_n += 1
                messages.append(
                    f"{tid!r}: deleted queue01 root ({task.capability_name!r}) and subtree."
                )
            else:  # pragma: no cover - defensive
                messages.append(f"{tid!r}: delete failed.")
        return ok_n, messages

    async def delete_queue01_task(
        self,
        *,
        task_id: str,
        capability_name: str,
    ) -> tuple[bool, str]:
        task = await self.get_task(task_id)
        if task is None:
            return False, "Task not found."
        if task.queue_name != TaskQueue.QUEUE01:
            return False, "Only queue01 (root business) tasks can be deleted with this tool."
        if task.capability_name != capability_name:
            return False, "Task belongs to another capability."
        deleted = await self.delete_task_tree(task_id)
        if not deleted:  # pragma: no cover - defensive
            return False, "Delete failed."
        return True, f"Deleted queue01 task {task_id!r} and all of its child tasks."

    async def delete_queue01_tasks_batch(
        self,
        *,
        task_ids: list[str],
        capability_name: str,
    ) -> tuple[int, list[str]]:
        """Delete multiple queue01 roots (each subtree). Returns (success_count, per-id messages)."""
        messages: list[str] = []
        ok_n = 0
        seen: set[str] = set()
        for raw in task_ids:
            tid = (raw or "").strip()
            if not tid or tid in seen:
                continue
            seen.add(tid)
            ok, msg = await self.delete_queue01_task(
                task_id=tid, capability_name=capability_name
            )
            if ok:
                ok_n += 1
            messages.append(msg)
        return ok_n, messages

    async def defer_queue02_task(
        self,
        *,
        task_id: str,
        capability_name: str,
        until: datetime,
    ) -> tuple[bool, str]:
        task = await self.get_task(task_id)
        if task is None:
            return False, "Task not found."
        if task.queue_name != TaskQueue.QUEUE02:
            return False, "Only queue02 (action) tasks can be deferred."
        if task.capability_name != capability_name:
            return False, "Task belongs to another capability."
        if task.status not in (TaskStatus.PENDING, TaskStatus.IN_PROGRESS):
            return False, "Task is already finished; it cannot be deferred."

        until_utc = until.astimezone(UTC) if until.tzinfo else until.replace(tzinfo=UTC)
        if until_utc <= datetime.now(UTC):
            return False, "The scheduled time must be strictly in the future (UTC)."

        now = self._now()
        async with self.database.connection() as conn:
            await conn.execute(
                """
                UPDATE tasks
                SET status = ?, agent_name = ?, claimed_at = ?, scheduled_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    TaskStatus.PENDING,
                    AgentName.ARCHITECT,
                    None,
                    until_utc.isoformat(),
                    now,
                    task_id,
                ),
            )
            await conn.commit()

        return (
            True,
            f"Deferred task {task_id!r} until {until_utc.isoformat()} (UTC). "
            "It will become claimable again at or after that time.",
        )

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

    async def list_tasklog(
        self,
        *,
        offset: int = 0,
        limit: int | None = None,
    ) -> list[TaskLogEntry]:
        """Return archived task trees from `tasklog`, newest first.

        When ``limit`` is ``None``, return all rows (used by ``GET /api/tasklog``).
        Otherwise apply ``LIMIT`` / ``OFFSET`` for pagination (``GET /api/log``).
        """
        base = (
            "SELECT id, root_id, capability_name, payload_json, created_at FROM tasklog "
            "ORDER BY created_at DESC, id DESC"
        )
        async with self.database.connection() as conn:
            if limit is None:
                cursor = await conn.execute(base)
            else:
                cursor = await conn.execute(f"{base} LIMIT ? OFFSET ?", (limit, offset))
            rows = await cursor.fetchall()

        out: list[TaskLogEntry] = []
        for row in rows:
            payload = json.loads(row["payload_json"])
            out.append(
                TaskLogEntry(
                    id=row["id"],
                    root_id=row["root_id"],
                    capability_name=row["capability_name"],
                    payload=payload,
                    created_at=datetime.fromisoformat(row["created_at"]),
                )
            )
        return out

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
        # Claim all pending LIFO tasks (newest first) before any FIFO task (oldest first).
        # See TaskQueuePolicy on TaskRecord / DecomposedRootTask / ArchitectTask.
        base_where = """
                WHERE queue_name = ? AND status = ? AND capability_name = ?
                  AND (scheduled_at IS NULL OR scheduled_at <= ?)
                  AND COALESCE(queue_policy, 'fifo') = ?
                """

        async with self.database.connection() as conn:
            await conn.execute("BEGIN IMMEDIATE")
            row = None
            for policy in (TaskQueuePolicy.LIFO, TaskQueuePolicy.FIFO):
                order_created = "DESC" if policy == TaskQueuePolicy.LIFO else "ASC"
                order_id = "DESC" if policy == TaskQueuePolicy.LIFO else "ASC"
                cursor = await conn.execute(
                    f"""
                    SELECT id
                    FROM tasks
                    {base_where}
                    ORDER BY created_at {order_created}, id {order_id}
                    LIMIT 1
                    """,
                    (queue_name, TaskStatus.PENDING, capability_name, now, policy.value),
                )
                row = await cursor.fetchone()
                if row is not None:
                    break

            if row is None:
                await conn.rollback()
                return None

            # Keep `scheduled_at` so the Implementer (and API) still see the Planner's target UTC
            # instant while the task is in progress; pending-queue selection uses status=pending only.
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
        root_id: str | None = None
        async with self.database.connection() as conn:
            cursor = await conn.execute("SELECT root_id FROM tasks WHERE id = ?", (task_id,))
            row = await cursor.fetchone()
            if row:
                root_id = row["root_id"]

            await conn.execute(
                """
                UPDATE tasks
                SET status = ?, result = ?, completed_at = ?, updated_at = ?, scheduled_at = NULL
                WHERE id = ?
                """,
                (TaskStatus.COMPLETED, result, now, now, task_id),
            )
            await conn.commit()

        if root_id:
            await self._maybe_archive_finished_tree(root_id)

    async def fail_task(self, task_id: str, *, error_message: str) -> None:
        now = self._now()
        root_id: str | None = None
        async with self.database.connection() as conn:
            cursor = await conn.execute("SELECT root_id FROM tasks WHERE id = ?", (task_id,))
            row = await cursor.fetchone()
            if row:
                root_id = row["root_id"]

            await conn.execute(
                """
                UPDATE tasks
                SET status = ?, result = ?, updated_at = ?, scheduled_at = NULL
                WHERE id = ?
                """,
                (TaskStatus.FAILED, error_message, now, task_id),
            )
            await conn.commit()

        if root_id:
            await self._maybe_archive_finished_tree(root_id)

    async def upwork_job_ids_already_processed(self, job_ids: list[str]) -> set[str]:
        """Return the subset of ``job_ids`` already stored in ``upwork_processed_jobs``."""
        cleaned = [str(x).strip() for x in job_ids if str(x).strip()]
        if not cleaned:
            return set()
        unique = list(dict.fromkeys(cleaned))
        placeholders = ",".join("?" * len(unique))
        async with self.database.connection() as conn:
            cursor = await conn.execute(
                f"SELECT job_id FROM upwork_processed_jobs WHERE job_id IN ({placeholders})",
                unique,
            )
            rows = await cursor.fetchall()
        return {str(r["job_id"]) for r in rows}

    async def mark_upwork_jobs_processed(self, job_ids: list[str]) -> None:
        """Record Upwork job IDs (dedupe keys) so future searches can skip AI re-triage."""
        cleaned = [str(x).strip() for x in job_ids if str(x).strip()]
        if not cleaned:
            return
        now = self._now()
        async with self.database.connection() as conn:
            for jid in dict.fromkeys(cleaned):
                await conn.execute(
                    """
                    INSERT OR IGNORE INTO upwork_processed_jobs (job_id, processed_at)
                    VALUES (?, ?)
                    """,
                    (jid, now),
                )
            await conn.commit()

    async def _maybe_archive_finished_tree(self, root_id: str) -> None:
        async with self.database.connection() as conn:
            await conn.execute("BEGIN IMMEDIATE")
            cursor = await conn.execute(
                "SELECT * FROM tasks WHERE root_id = ? ORDER BY created_at ASC, id ASC",
                (root_id,),
            )
            rows = await cursor.fetchall()
            if not rows:
                await conn.rollback()
                return

            records = [self._to_record(row) for row in rows]
            if any(
                r.status not in (TaskStatus.COMPLETED, TaskStatus.FAILED) for r in records
            ):
                await conn.rollback()
                return

            tree = self._single_tree_from_records(records)
            capability_name = next(
                (r.capability_name for r in records if r.id == root_id),
                records[0].capability_name,
            )
            log_id = str(uuid4())
            now = self._now()
            payload_json = tree.model_dump_json()
            await conn.execute(
                """
                INSERT INTO tasklog (id, root_id, capability_name, payload_json, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (log_id, root_id, capability_name, payload_json, now),
            )
            await conn.execute("DELETE FROM tasks WHERE root_id = ?", (root_id,))
            await conn.commit()

    @staticmethod
    def _single_tree_from_records(records: list[TaskRecord]) -> TaskTree:
        nodes = {r.id: TaskTree(**r.model_dump(), children=[]) for r in records}
        roots: list[TaskTree] = []
        for item in sorted(records, key=lambda r: (r.created_at, r.id)):
            node = nodes[item.id]
            if item.parent_id and item.parent_id in nodes:
                nodes[item.parent_id].children.append(node)
            else:
                roots.append(node)
        if len(roots) != 1:
            raise RuntimeError("Expected exactly one root in archived subtree.")
        return roots[0]

    @staticmethod
    def _to_record(row: object) -> TaskRecord:
        return TaskRecord.model_validate(dict(row))

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat()

    @staticmethod
    def _dt_to_iso(value: datetime | None) -> str | None:
        if value is None:
            return None
        dt = value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)
        return dt.isoformat()
