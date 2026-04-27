from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import uuid4

from vossploee.database import Database
from vossploee.models import Message, RoleTask, TaskRecord, TaskStatus, TaskTree, UserRef


class TaskRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    async def create_root_tasks(self, roots: list[RoleTask]) -> list[TaskRecord]:
        created: list[TaskRecord] = []
        for root in roots:
            task_id = str(uuid4())
            now = self._now()
            capability_id = root.role_id.split(".", 1)[0]
            async with self.database.connection() as conn:
                await conn.execute(
                    """
                    INSERT INTO tasks (
                        id, parent_id, root_id, role_id, capability_id, title, description,
                        payload_json, status, queue_policy, scheduled_at, refining_user_json,
                        result, created_at, updated_at, claimed_at, completed_at
                    ) VALUES (?, NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, ?, ?, NULL, NULL)
                    """,
                    (
                        task_id,
                        task_id,
                        root.role_id,
                        capability_id,
                        root.title,
                        root.description,
                        json.dumps(root.payload),
                        TaskStatus.PENDING.value,
                        root.queue_policy,
                        self._dt_to_iso(root.scheduled_at),
                        now,
                        now,
                    ),
                )
                await conn.commit()
            maybe = await self.get_task(task_id)
            if maybe:
                created.append(maybe)
        return created

    async def create_child_tasks(self, *, parent: TaskRecord, tasks: list[RoleTask]) -> list[TaskRecord]:
        created: list[TaskRecord] = []
        for child in tasks:
            child_id = str(uuid4())
            now = self._now()
            capability_id = child.role_id.split(".", 1)[0]
            async with self.database.connection() as conn:
                await conn.execute(
                    """
                    INSERT INTO tasks (
                        id, parent_id, root_id, role_id, capability_id, title, description,
                        payload_json, status, queue_policy, scheduled_at, refining_user_json,
                        result, created_at, updated_at, claimed_at, completed_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, ?, ?, NULL, NULL)
                    """,
                    (
                        child_id,
                        str(parent.id),
                        str(parent.root_id),
                        child.role_id,
                        capability_id,
                        child.title,
                        child.description,
                        json.dumps(child.payload),
                        TaskStatus.PENDING.value,
                        child.queue_policy,
                        self._dt_to_iso(child.scheduled_at),
                        now,
                        now,
                    ),
                )
                await conn.commit()
            maybe = await self.get_task(child_id)
            if maybe:
                created.append(maybe)
        return created

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

    async def claim_next_task(self, *, role_id: str, now: datetime) -> TaskRecord | None:
        now_iso = now.astimezone(UTC).isoformat()
        async with self.database.connection() as conn:
            await conn.execute("BEGIN IMMEDIATE")
            row = None
            for policy, created_order in (("lifo", "DESC"), ("fifo", "ASC")):
                cursor = await conn.execute(
                    f"""
                    SELECT id FROM tasks
                    WHERE status = ? AND role_id = ? AND (scheduled_at IS NULL OR scheduled_at <= ?)
                      AND queue_policy = ?
                    ORDER BY created_at {created_order}, id {created_order}
                    LIMIT 1
                    """,
                    (TaskStatus.PENDING.value, role_id, now_iso, policy),
                )
                row = await cursor.fetchone()
                if row:
                    break
            if not row:
                await conn.rollback()
                return None
            await conn.execute(
                "UPDATE tasks SET status=?, claimed_at=?, updated_at=? WHERE id=?",
                (TaskStatus.IN_PROGRESS.value, now_iso, now_iso, row["id"]),
            )
            cursor = await conn.execute("SELECT * FROM tasks WHERE id=?", (row["id"],))
            claimed = await cursor.fetchone()
            await conn.commit()
        return self._to_record(claimed) if claimed else None

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
    ) -> list[dict[str, object]]:
        base = (
            "SELECT id, root_id, payload_json, created_at FROM tasklog "
            "ORDER BY created_at DESC, id DESC"
        )
        async with self.database.connection() as conn:
            if limit is None:
                cursor = await conn.execute(base)
            else:
                cursor = await conn.execute(f"{base} LIMIT ? OFFSET ?", (limit, offset))
            rows = await cursor.fetchall()

        out: list[dict[str, object]] = []
        for row in rows:
            payload = json.loads(row["payload_json"])
            out.append(
                {"id": row["id"], "root_id": row["root_id"], "payload": payload, "created_at": row["created_at"]}
            )
        return out

    async def delete_task_tree(self, task_id: str) -> bool:
        async with self.database.connection() as conn:
            cursor = await conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
            await conn.commit()
            return cursor.rowcount > 0

    async def complete_task(self, task_id: str, *, result: str) -> None:
        await self._set_terminal(task_id=task_id, status=TaskStatus.COMPLETED, result=result)

    async def fail_task(self, task_id: str, *, error_message: str) -> None:
        await self._set_terminal(task_id=task_id, status=TaskStatus.FAILED, result=error_message)

    async def set_refining(self, *, task_id: str, user: UserRef) -> None:
        now = self._now()
        async with self.database.connection() as conn:
            await conn.execute(
                "UPDATE tasks SET status=?, refining_user_json=?, updated_at=? WHERE id=?",
                (TaskStatus.REFINING.value, user.model_dump_json(), now, task_id),
            )
            await conn.commit()

    async def resume_refining(self, task_id: str, answer: Message) -> None:
        task = await self.get_task(task_id)
        if not task:
            return
        payload = dict(task.payload)
        refinements = payload.setdefault("refinement", [])
        refinements.append(answer.model_dump(mode="json"))
        now = self._now()
        async with self.database.connection() as conn:
            await conn.execute(
                "UPDATE tasks SET status=?, payload_json=?, refining_user_json=NULL, updated_at=? WHERE id=?",
                (TaskStatus.PENDING.value, json.dumps(payload), now, task_id),
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
            log_id = str(uuid4())
            now = self._now()
            payload_json = tree.model_dump_json()
            await conn.execute(
                """
                INSERT INTO tasklog (id, root_id, payload_json, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (log_id, root_id, payload_json, now),
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
        raw = dict(row)
        raw["payload"] = json.loads(raw.pop("payload_json") or "{}")
        refining_raw = raw.pop("refining_user_json")
        raw["refining_until_user"] = json.loads(refining_raw) if refining_raw else None
        return TaskRecord.model_validate(raw)

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat()

    @staticmethod
    def _dt_to_iso(value: datetime | None) -> str | None:
        if value is None:
            return None
        dt = value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)
        return dt.isoformat()

    async def _set_terminal(self, *, task_id: str, status: TaskStatus, result: str) -> None:
        now = self._now()
        root_id: str | None = None
        async with self.database.connection() as conn:
            cursor = await conn.execute("SELECT root_id FROM tasks WHERE id=?", (task_id,))
            row = await cursor.fetchone()
            if row:
                root_id = row["root_id"]
            await conn.execute(
                "UPDATE tasks SET status=?, result=?, completed_at=?, updated_at=?, scheduled_at=NULL WHERE id=?",
                (status.value, result, now, now, task_id),
            )
            await conn.commit()
        if root_id:
            await self._maybe_archive_finished_tree(root_id)


class ChannelRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    async def create_message(
        self,
        *,
        channel_id: str,
        sender: UserRef,
        receiver: UserRef,
        body: dict[str, object],
        in_reply_to: str | None = None,
        task_id: str | None = None,
        dedupe_key: str | None = None,
    ) -> Message:
        msg_id = str(uuid4())
        now = datetime.now(UTC).isoformat()
        async with self.database.connection() as conn:
            await conn.execute(
                """
                INSERT OR IGNORE INTO channel_messages
                (id, channel_id, sender_json, receiver_json, body_json, in_reply_to, task_id, dedupe_key, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    msg_id,
                    channel_id,
                    sender.model_dump_json(),
                    receiver.model_dump_json(),
                    json.dumps(body),
                    in_reply_to,
                    task_id,
                    dedupe_key,
                    now,
                ),
            )
            await conn.commit()
        return Message.model_validate(
            {
                "id": msg_id,
                "channel_id": channel_id,
                "sender": sender.model_dump(),
                "receiver": receiver.model_dump(),
                "body": body,
                "in_reply_to": in_reply_to,
                "task_id": task_id,
                "created_at": now,
            }
        )

    async def list_messages(self, *, channel_id: str, user_id: str, n: int = 50) -> list[Message]:
        async with self.database.connection() as conn:
            cursor = await conn.execute(
                """
                SELECT * FROM channel_messages
                WHERE channel_id=? AND (json_extract(sender_json, '$.user_id')=? OR json_extract(receiver_json, '$.user_id')=?)
                ORDER BY created_at DESC LIMIT ?
                """,
                (channel_id, user_id, user_id, n),
            )
            rows = await cursor.fetchall()
        out: list[Message] = []
        for row in rows:
            out.append(
                Message.model_validate(
                    {
                        "id": row["id"],
                        "channel_id": row["channel_id"],
                        "sender": json.loads(row["sender_json"]),
                        "receiver": json.loads(row["receiver_json"]),
                        "body": json.loads(row["body_json"]),
                        "in_reply_to": row["in_reply_to"],
                        "task_id": row["task_id"],
                        "created_at": row["created_at"],
                    }
                )
            )
        return out
