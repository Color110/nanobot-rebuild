from __future__ import annotations

import asyncio
import hashlib
import json
import sqlite3
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from app.orchestration.graph import ResolvedTaskGraph
from app.orchestration.models import (
    RuntimeTask,
    TaskError,
    TaskResult,
    TaskStatus,
    WorkflowStatus,
)


_TERMINAL_TASK_STATUSES = {
    TaskStatus.SUCCEEDED,
    TaskStatus.FAILED,
    TaskStatus.TIMED_OUT,
    TaskStatus.CANCELLED,
    TaskStatus.SKIPPED,
}


class TaskStoreError(RuntimeError):
    """Base error for durable orchestration state."""


class WorkflowNotFoundError(TaskStoreError):
    pass


class TaskNotFoundError(TaskStoreError):
    pass


class StoreConflictError(TaskStoreError):
    pass


@dataclass(frozen=True)
class StoredTask:
    task: RuntimeTask
    result: TaskResult | None
    worker_id: str | None
    lease_until: float | None
    last_heartbeat: float | None

    @property
    def lease_expired(self) -> bool:
        return (
            self.task.status == TaskStatus.RUNNING
            and self.lease_until is not None
            and self.lease_until <= time.time()
        )


@dataclass(frozen=True)
class WorkflowSnapshot:
    workflow_id: str
    status: WorkflowStatus
    deadline_at: float
    topological_order: tuple[str, ...]
    depth_by_task: dict[str, int]
    tasks: dict[str, StoredTask]
    created_at: float
    updated_at: float

    @property
    def task_states(self) -> dict[str, RuntimeTask]:
        return {task_id: record.task for task_id, record in self.tasks.items()}

    @property
    def task_results(self) -> dict[str, TaskResult]:
        return {
            task_id: record.result
            for task_id, record in self.tasks.items()
            if record.result is not None
        }


class TaskStore(ABC):
    """Durable source of truth for one or more orchestration workflows."""

    @abstractmethod
    async def create_workflow(
        self,
        graph: ResolvedTaskGraph,
        *,
        deadline_at: float,
    ) -> WorkflowSnapshot:
        raise NotImplementedError

    @abstractmethod
    async def load_workflow(self, workflow_id: str) -> WorkflowSnapshot:
        raise NotImplementedError

    @abstractmethod
    async def list_active_workflow_ids(self) -> tuple[str, ...]:
        raise NotImplementedError

    @abstractmethod
    async def set_workflow_status(
        self,
        workflow_id: str,
        status: WorkflowStatus,
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    async def transition_task(
        self,
        workflow_id: str,
        task_id: str,
        *,
        expected_statuses: Iterable[TaskStatus],
        new_status: TaskStatus,
        result: TaskResult | None = None,
    ) -> RuntimeTask | None:
        """Compare-and-set transition. Returns None when expected state lost."""
        raise NotImplementedError

    @abstractmethod
    async def claim_task(
        self,
        workflow_id: str,
        task_id: str,
        *,
        worker_id: str,
        lease_seconds: float,
        max_concurrency: int,
    ) -> RuntimeTask | None:
        """Atomically READY -> RUNNING and increment attempt."""
        raise NotImplementedError

    @abstractmethod
    async def heartbeat(
        self,
        workflow_id: str,
        task_id: str,
        *,
        worker_id: str,
        lease_seconds: float,
    ) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def finish_task(
        self,
        workflow_id: str,
        task_id: str,
        *,
        worker_id: str,
        result: TaskResult,
    ) -> RuntimeTask | None:
        """Commit a terminal result only while this worker still owns the lease."""
        raise NotImplementedError

    @abstractmethod
    async def recover_expired_task(
        self,
        workflow_id: str,
        task_id: str,
        *,
        retry: bool,
        failure_result: TaskResult | None = None,
    ) -> RuntimeTask | None:
        """Recover only if RUNNING lease is expired at commit time."""
        raise NotImplementedError

    @abstractmethod
    async def cancel_nonterminal_tasks(
        self,
        workflow_id: str,
        *,
        code: str,
        message: str,
    ) -> int:
        raise NotImplementedError


class SQLiteTaskStore(TaskStore):
    """
    Durable SQLite TaskStore.

    Each operation uses a short-lived connection. Claim/recovery transitions use
    BEGIN IMMEDIATE so multiple scheduler processes cannot claim the same task or
    exceed workflow max_concurrency through a read-then-write race.
    """

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        if str(self._path) == ":memory:":
            raise ValueError(
                "SQLiteTaskStore 不支持 :memory:；M5 需要真正可跨进程重启恢复的文件数据库"
            )
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(
            self._path,
            timeout=30.0,
            isolation_level=None,
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 30000")
        return conn

    def _initialize_schema(self) -> None:
        with self._connect() as conn:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA synchronous = NORMAL")
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS workflows (
                    workflow_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    deadline_at REAL NOT NULL,
                    topological_order_json TEXT NOT NULL,
                    depth_by_task_json TEXT NOT NULL,
                    graph_hash TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS tasks (
                    workflow_id TEXT NOT NULL,
                    task_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    attempt INTEGER NOT NULL,
                    task_json TEXT NOT NULL,
                    result_json TEXT,
                    worker_id TEXT,
                    lease_until REAL,
                    last_heartbeat REAL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    PRIMARY KEY (workflow_id, task_id),
                    FOREIGN KEY (workflow_id)
                        REFERENCES workflows(workflow_id)
                        ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_tasks_workflow_status
                    ON tasks(workflow_id, status);

                CREATE INDEX IF NOT EXISTS idx_tasks_expired_lease
                    ON tasks(status, lease_until);
                """
            )

    @staticmethod
    def _task_json(task: RuntimeTask) -> str:
        return json.dumps(
            task.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )

    @staticmethod
    def _result_json(result: TaskResult) -> str:
        return json.dumps(
            result.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )

    @staticmethod
    def _graph_hash(graph: ResolvedTaskGraph) -> str:
        payload = {
            "workflow_id": graph.workflow_id,
            "topological_order": list(graph.topological_order),
            "depth_by_task": graph.depth_by_task,
            "tasks": [
                task.model_dump(
                    mode="json",
                    exclude={"status", "attempt"},
                )
                for task in sorted(graph.tasks, key=lambda item: item.task_id)
            ],
        }
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    async def create_workflow(
        self,
        graph: ResolvedTaskGraph,
        *,
        deadline_at: float,
    ) -> WorkflowSnapshot:
        return await asyncio.to_thread(
            self._create_workflow_sync,
            graph,
            deadline_at,
        )

    def _create_workflow_sync(
        self,
        graph: ResolvedTaskGraph,
        deadline_at: float,
    ) -> WorkflowSnapshot:
        if deadline_at <= time.time():
            raise ValueError("deadline_at 必须晚于当前时间")

        for task in graph.tasks:
            if task.workflow_id != graph.workflow_id:
                raise StoreConflictError(
                    f"Task {task.task_id} workflow_id 与 graph 不一致"
                )
            if task.status != TaskStatus.PENDING or task.attempt != 0:
                raise StoreConflictError(
                    "新建 Workflow 时 RuntimeTask 必须从 PENDING/attempt=0 开始"
                )

        graph_hash = self._graph_hash(graph)
        now = time.time()

        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            existing = conn.execute(
                "SELECT graph_hash FROM workflows WHERE workflow_id = ?",
                (graph.workflow_id,),
            ).fetchone()

            if existing is not None:
                if existing["graph_hash"] != graph_hash:
                    conn.execute("ROLLBACK")
                    raise StoreConflictError(
                        f"workflow_id={graph.workflow_id!r} 已存在，但 Task Graph 不一致"
                    )
                conn.execute("COMMIT")
                return self._load_workflow_sync(graph.workflow_id)

            conn.execute(
                """
                INSERT INTO workflows(
                    workflow_id, status, deadline_at,
                    topological_order_json, depth_by_task_json,
                    graph_hash, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    graph.workflow_id,
                    WorkflowStatus.PENDING.value,
                    deadline_at,
                    json.dumps(list(graph.topological_order)),
                    json.dumps(graph.depth_by_task, sort_keys=True),
                    graph_hash,
                    now,
                    now,
                ),
            )

            for task in graph.tasks:
                conn.execute(
                    """
                    INSERT INTO tasks(
                        workflow_id, task_id, status, attempt,
                        task_json, result_json,
                        worker_id, lease_until, last_heartbeat,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, NULL, NULL, NULL, NULL, ?, ?)
                    """,
                    (
                        graph.workflow_id,
                        task.task_id,
                        task.status.value,
                        task.attempt,
                        self._task_json(task),
                        now,
                        now,
                    ),
                )

            conn.execute("COMMIT")

        return self._load_workflow_sync(graph.workflow_id)

    async def load_workflow(self, workflow_id: str) -> WorkflowSnapshot:
        return await asyncio.to_thread(self._load_workflow_sync, workflow_id)

    def _load_workflow_sync(self, workflow_id: str) -> WorkflowSnapshot:
        with self._connect() as conn:
            workflow = conn.execute(
                "SELECT * FROM workflows WHERE workflow_id = ?",
                (workflow_id,),
            ).fetchone()
            if workflow is None:
                raise WorkflowNotFoundError(workflow_id)

            task_rows = conn.execute(
                "SELECT * FROM tasks WHERE workflow_id = ? ORDER BY task_id",
                (workflow_id,),
            ).fetchall()

        records: dict[str, StoredTask] = {}
        for row in task_rows:
            task = RuntimeTask.model_validate_json(row["task_json"])
            result = (
                TaskResult.model_validate_json(row["result_json"])
                if row["result_json"] is not None
                else None
            )
            records[task.task_id] = StoredTask(
                task=task,
                result=result,
                worker_id=row["worker_id"],
                lease_until=row["lease_until"],
                last_heartbeat=row["last_heartbeat"],
            )

        return WorkflowSnapshot(
            workflow_id=workflow["workflow_id"],
            status=WorkflowStatus(workflow["status"]),
            deadline_at=float(workflow["deadline_at"]),
            topological_order=tuple(
                json.loads(workflow["topological_order_json"])
            ),
            depth_by_task={
                str(key): int(value)
                for key, value in json.loads(
                    workflow["depth_by_task_json"]
                ).items()
            },
            tasks=records,
            created_at=float(workflow["created_at"]),
            updated_at=float(workflow["updated_at"]),
        )

    async def list_active_workflow_ids(self) -> tuple[str, ...]:
        return await asyncio.to_thread(self._list_active_workflow_ids_sync)

    def _list_active_workflow_ids_sync(self) -> tuple[str, ...]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT workflow_id
                FROM workflows
                WHERE status IN (?, ?)
                ORDER BY created_at
                """,
                (
                    WorkflowStatus.PENDING.value,
                    WorkflowStatus.RUNNING.value,
                ),
            ).fetchall()
        return tuple(row["workflow_id"] for row in rows)

    async def set_workflow_status(
        self,
        workflow_id: str,
        status: WorkflowStatus,
    ) -> None:
        await asyncio.to_thread(
            self._set_workflow_status_sync,
            workflow_id,
            status,
        )

    def _set_workflow_status_sync(
        self,
        workflow_id: str,
        status: WorkflowStatus,
    ) -> None:
        now = time.time()
        with self._connect() as conn:
            cursor = conn.execute(
                """
                UPDATE workflows
                SET status = ?, updated_at = ?
                WHERE workflow_id = ?
                """,
                (status.value, now, workflow_id),
            )
            if cursor.rowcount != 1:
                raise WorkflowNotFoundError(workflow_id)

    async def transition_task(
        self,
        workflow_id: str,
        task_id: str,
        *,
        expected_statuses: Iterable[TaskStatus],
        new_status: TaskStatus,
        result: TaskResult | None = None,
    ) -> RuntimeTask | None:
        expected = tuple(status.value for status in expected_statuses)
        if not expected:
            raise ValueError("expected_statuses 不能为空")
        return await asyncio.to_thread(
            self._transition_task_sync,
            workflow_id,
            task_id,
            expected,
            new_status,
            result,
        )

    def _transition_task_sync(
        self,
        workflow_id: str,
        task_id: str,
        expected: tuple[str, ...],
        new_status: TaskStatus,
        result: TaskResult | None,
    ) -> RuntimeTask | None:
        now = time.time()
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                """
                SELECT task_json, status
                FROM tasks
                WHERE workflow_id = ? AND task_id = ?
                """,
                (workflow_id, task_id),
            ).fetchone()
            if row is None:
                conn.execute("ROLLBACK")
                raise TaskNotFoundError(f"{workflow_id}/{task_id}")

            if row["status"] not in expected:
                conn.execute("COMMIT")
                return None

            if result is not None:
                if (
                    result.workflow_id != workflow_id
                    or result.task_id != task_id
                    or result.status != new_status
                ):
                    conn.execute("ROLLBACK")
                    raise StoreConflictError(
                        "TaskResult identity/status 与 transition 不一致"
                    )

            task = RuntimeTask.model_validate_json(row["task_json"])
            updated = task.model_copy(update={"status": new_status})
            terminal = new_status in _TERMINAL_TASK_STATUSES

            conn.execute(
                """
                UPDATE tasks
                SET status = ?, task_json = ?, result_json = ?,
                    worker_id = CASE WHEN ? THEN NULL ELSE worker_id END,
                    lease_until = CASE WHEN ? THEN NULL ELSE lease_until END,
                    last_heartbeat = CASE WHEN ? THEN NULL ELSE last_heartbeat END,
                    updated_at = ?
                WHERE workflow_id = ? AND task_id = ?
                """,
                (
                    new_status.value,
                    self._task_json(updated),
                    self._result_json(result) if result is not None else None,
                    int(terminal),
                    int(terminal),
                    int(terminal),
                    now,
                    workflow_id,
                    task_id,
                ),
            )
            conn.execute("COMMIT")
            return updated

    async def claim_task(
        self,
        workflow_id: str,
        task_id: str,
        *,
        worker_id: str,
        lease_seconds: float,
        max_concurrency: int,
    ) -> RuntimeTask | None:
        if lease_seconds <= 0:
            raise ValueError("lease_seconds 必须大于 0")
        if max_concurrency <= 0:
            raise ValueError("max_concurrency 必须大于 0")
        return await asyncio.to_thread(
            self._claim_task_sync,
            workflow_id,
            task_id,
            worker_id,
            lease_seconds,
            max_concurrency,
        )

    def _claim_task_sync(
        self,
        workflow_id: str,
        task_id: str,
        worker_id: str,
        lease_seconds: float,
        max_concurrency: int,
    ) -> RuntimeTask | None:
        now = time.time()
        lease_until = now + lease_seconds

        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")

            workflow = conn.execute(
                "SELECT status FROM workflows WHERE workflow_id = ?",
                (workflow_id,),
            ).fetchone()
            if workflow is None:
                conn.execute("ROLLBACK")
                raise WorkflowNotFoundError(workflow_id)
            if workflow["status"] != WorkflowStatus.RUNNING.value:
                conn.execute("COMMIT")
                return None

            running_count = conn.execute(
                """
                SELECT COUNT(*) AS count
                FROM tasks
                WHERE workflow_id = ? AND status = ?
                """,
                (workflow_id, TaskStatus.RUNNING.value),
            ).fetchone()["count"]

            if int(running_count) >= max_concurrency:
                conn.execute("COMMIT")
                return None

            row = conn.execute(
                """
                SELECT task_json, status
                FROM tasks
                WHERE workflow_id = ? AND task_id = ?
                """,
                (workflow_id, task_id),
            ).fetchone()
            if row is None:
                conn.execute("ROLLBACK")
                raise TaskNotFoundError(f"{workflow_id}/{task_id}")
            if row["status"] != TaskStatus.READY.value:
                conn.execute("COMMIT")
                return None

            task = RuntimeTask.model_validate_json(row["task_json"])
            updated = task.model_copy(
                update={
                    "status": TaskStatus.RUNNING,
                    "attempt": task.attempt + 1,
                }
            )

            conn.execute(
                """
                UPDATE tasks
                SET status = ?, attempt = ?, task_json = ?,
                    worker_id = ?, lease_until = ?, last_heartbeat = ?,
                    updated_at = ?
                WHERE workflow_id = ? AND task_id = ?
                """,
                (
                    TaskStatus.RUNNING.value,
                    updated.attempt,
                    self._task_json(updated),
                    worker_id,
                    lease_until,
                    now,
                    now,
                    workflow_id,
                    task_id,
                ),
            )
            conn.execute("COMMIT")
            return updated

    async def heartbeat(
        self,
        workflow_id: str,
        task_id: str,
        *,
        worker_id: str,
        lease_seconds: float,
    ) -> bool:
        return await asyncio.to_thread(
            self._heartbeat_sync,
            workflow_id,
            task_id,
            worker_id,
            lease_seconds,
        )

    def _heartbeat_sync(
        self,
        workflow_id: str,
        task_id: str,
        worker_id: str,
        lease_seconds: float,
    ) -> bool:
        now = time.time()
        with self._connect() as conn:
            cursor = conn.execute(
                """
                UPDATE tasks
                SET lease_until = ?, last_heartbeat = ?, updated_at = ?
                WHERE workflow_id = ?
                  AND task_id = ?
                  AND status = ?
                  AND worker_id = ?
                  AND lease_until > ?
                  AND EXISTS (
                      SELECT 1 FROM workflows w
                      WHERE w.workflow_id = tasks.workflow_id
                        AND w.status = ?
                  )
                """,
                (
                    now + lease_seconds,
                    now,
                    now,
                    workflow_id,
                    task_id,
                    TaskStatus.RUNNING.value,
                    worker_id,
                    now,
                    WorkflowStatus.RUNNING.value,
                ),
            )
            return cursor.rowcount == 1

    async def finish_task(
        self,
        workflow_id: str,
        task_id: str,
        *,
        worker_id: str,
        result: TaskResult,
    ) -> RuntimeTask | None:
        return await asyncio.to_thread(
            self._finish_task_sync,
            workflow_id,
            task_id,
            worker_id,
            result,
        )

    def _finish_task_sync(
        self,
        workflow_id: str,
        task_id: str,
        worker_id: str,
        result: TaskResult,
    ) -> RuntimeTask | None:
        if result.workflow_id != workflow_id or result.task_id != task_id:
            raise StoreConflictError("TaskResult identity 与 finish_task 不一致")

        now = time.time()
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                """
                SELECT task_json, status, worker_id, lease_until
                FROM tasks
                WHERE workflow_id = ? AND task_id = ?
                """,
                (workflow_id, task_id),
            ).fetchone()
            if row is None:
                conn.execute("ROLLBACK")
                raise TaskNotFoundError(f"{workflow_id}/{task_id}")

            workflow = conn.execute(
                "SELECT status FROM workflows WHERE workflow_id = ?",
                (workflow_id,),
            ).fetchone()

            owns_live_lease = (
                row["status"] == TaskStatus.RUNNING.value
                and row["worker_id"] == worker_id
                and row["lease_until"] is not None
                and float(row["lease_until"]) > now
                and workflow is not None
                and workflow["status"] == WorkflowStatus.RUNNING.value
            )
            if not owns_live_lease:
                conn.execute("COMMIT")
                return None

            task = RuntimeTask.model_validate_json(row["task_json"])
            updated = task.model_copy(update={"status": result.status})

            conn.execute(
                """
                UPDATE tasks
                SET status = ?, task_json = ?, result_json = ?,
                    worker_id = NULL, lease_until = NULL,
                    last_heartbeat = NULL, updated_at = ?
                WHERE workflow_id = ? AND task_id = ?
                """,
                (
                    result.status.value,
                    self._task_json(updated),
                    self._result_json(result),
                    now,
                    workflow_id,
                    task_id,
                ),
            )
            conn.execute("COMMIT")
            return updated

    async def recover_expired_task(
        self,
        workflow_id: str,
        task_id: str,
        *,
        retry: bool,
        failure_result: TaskResult | None = None,
    ) -> RuntimeTask | None:
        return await asyncio.to_thread(
            self._recover_expired_task_sync,
            workflow_id,
            task_id,
            retry,
            failure_result,
        )

    def _recover_expired_task_sync(
        self,
        workflow_id: str,
        task_id: str,
        retry: bool,
        failure_result: TaskResult | None,
    ) -> RuntimeTask | None:
        now = time.time()
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                """
                SELECT task_json, status, lease_until
                FROM tasks
                WHERE workflow_id = ? AND task_id = ?
                """,
                (workflow_id, task_id),
            ).fetchone()
            if row is None:
                conn.execute("ROLLBACK")
                raise TaskNotFoundError(f"{workflow_id}/{task_id}")

            expired = (
                row["status"] == TaskStatus.RUNNING.value
                and row["lease_until"] is not None
                and float(row["lease_until"]) <= now
            )
            if not expired:
                conn.execute("COMMIT")
                return None

            task = RuntimeTask.model_validate_json(row["task_json"])

            if retry:
                updated = task.model_copy(update={"status": TaskStatus.READY})
                result_json = None
            else:
                if failure_result is None:
                    conn.execute("ROLLBACK")
                    raise ValueError("retry=False 时必须提供 failure_result")
                if (
                    failure_result.workflow_id != workflow_id
                    or failure_result.task_id != task_id
                    or failure_result.status != TaskStatus.FAILED
                ):
                    conn.execute("ROLLBACK")
                    raise StoreConflictError(
                        "expired task failure_result 必须对应当前 Task 且状态为 FAILED"
                    )
                updated = task.model_copy(update={"status": TaskStatus.FAILED})
                result_json = self._result_json(failure_result)

            conn.execute(
                """
                UPDATE tasks
                SET status = ?, task_json = ?, result_json = ?,
                    worker_id = NULL, lease_until = NULL,
                    last_heartbeat = NULL, updated_at = ?
                WHERE workflow_id = ? AND task_id = ?
                """,
                (
                    updated.status.value,
                    self._task_json(updated),
                    result_json,
                    now,
                    workflow_id,
                    task_id,
                ),
            )
            conn.execute("COMMIT")
            return updated

    async def cancel_nonterminal_tasks(
        self,
        workflow_id: str,
        *,
        code: str,
        message: str,
    ) -> int:
        return await asyncio.to_thread(
            self._cancel_nonterminal_tasks_sync,
            workflow_id,
            code,
            message,
        )

    def _cancel_nonterminal_tasks_sync(
        self,
        workflow_id: str,
        code: str,
        message: str,
    ) -> int:
        now = time.time()
        terminal_values = {status.value for status in _TERMINAL_TASK_STATUSES}
        count = 0

        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            workflow = conn.execute(
                "SELECT 1 FROM workflows WHERE workflow_id = ?",
                (workflow_id,),
            ).fetchone()
            if workflow is None:
                conn.execute("ROLLBACK")
                raise WorkflowNotFoundError(workflow_id)

            rows = conn.execute(
                "SELECT task_json, status FROM tasks WHERE workflow_id = ?",
                (workflow_id,),
            ).fetchall()

            for row in rows:
                if row["status"] in terminal_values:
                    continue

                task = RuntimeTask.model_validate_json(row["task_json"])
                ambiguous = task.status == TaskStatus.RUNNING
                result = TaskResult(
                    workflow_id=task.workflow_id,
                    task_id=task.task_id,
                    status=TaskStatus.CANCELLED,
                    summary="Task cancelled by workflow-level control",
                    error=TaskError(
                        code=code,
                        message=message,
                        retryable=False,
                        ambiguous_side_effect=ambiguous,
                    ),
                )
                updated = task.model_copy(update={"status": TaskStatus.CANCELLED})

                conn.execute(
                    """
                    UPDATE tasks
                    SET status = ?, task_json = ?, result_json = ?,
                        worker_id = NULL, lease_until = NULL,
                        last_heartbeat = NULL, updated_at = ?
                    WHERE workflow_id = ? AND task_id = ?
                    """,
                    (
                        TaskStatus.CANCELLED.value,
                        self._task_json(updated),
                        self._result_json(result),
                        now,
                        workflow_id,
                        task.task_id,
                    ),
                )
                count += 1

            conn.execute(
                """
                UPDATE workflows
                SET status = ?, updated_at = ?
                WHERE workflow_id = ?
                """,
                (WorkflowStatus.CANCELLED.value, now, workflow_id),
            )
            conn.execute("COMMIT")

        return count
