from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from enum import StrEnum
from typing import Callable, Protocol
from uuid import uuid4

from app.orchestration.graph import ResolvedTaskGraph
from app.orchestration.models import (
    RuntimeTask,
    TaskError,
    TaskResult,
    TaskStatus,
    WorkflowStatus,
)
from app.orchestration.policy import OrchestrationPolicy
from app.orchestration.store import (
    StoredTask,
    TaskStore,
    WorkflowSnapshot,
)
from app.orchestration.tracing import (
    NullTraceSink,
    TraceEventType,
    TraceSink,
    emit_trace,
    new_trace_id,
)


_TERMINAL_TASK_STATUSES = {
    TaskStatus.SUCCEEDED,
    TaskStatus.FAILED,
    TaskStatus.TIMED_OUT,
    TaskStatus.CANCELLED,
    TaskStatus.SKIPPED,
}

_BLOCKING_DEPENDENCY_STATUSES = {
    TaskStatus.FAILED,
    TaskStatus.TIMED_OUT,
    TaskStatus.CANCELLED,
    TaskStatus.SKIPPED,
}


class SchedulerInvariantError(RuntimeError):
    pass


class RecoveryAction(StrEnum):
    RETRY = "RETRY"
    FAIL_CLOSED = "FAIL_CLOSED"


RecoveryDecider = Callable[[RuntimeTask], RecoveryAction]


class TaskExecutor(Protocol):
    async def execute(
        self,
        task: RuntimeTask,
        *,
        dependency_results: dict[str, TaskResult] | None = None,
        trace_id: str | None = None,
    ) -> TaskResult: ...


def fail_closed_recovery(_: RuntimeTask) -> RecoveryAction:
    """Safe default while task/tool idempotency metadata is unavailable."""
    return RecoveryAction.FAIL_CLOSED


@dataclass(frozen=True)
class WorkflowRunResult:
    workflow_id: str
    status: WorkflowStatus
    task_results: dict[str, TaskResult]
    task_states: dict[str, RuntimeTask]

    def result_for(self, task_id: str) -> TaskResult | None:
        return self.task_results.get(task_id)


@dataclass(frozen=True)
class _LocalExecutionOutcome:
    result: TaskResult
    lease_lost: bool = False


class TaskScheduler:
    """
    Durable DAG scheduler.

    The SQLite/TaskStore is the source of truth. Local dicts only track
    coroutines currently owned by this worker process.
    """

    def __init__(
        self,
        *,
        executor: TaskExecutor,
        policy: OrchestrationPolicy,
        store: TaskStore,
        worker_id: str | None = None,
        lease_seconds: float = 30.0,
        heartbeat_interval_seconds: float = 10.0,
        poll_interval_seconds: float = 0.25,
        recovery_decider: RecoveryDecider | None = None,
        trace_sink: TraceSink | None = None,
    ) -> None:
        if lease_seconds <= 0:
            raise ValueError("lease_seconds 必须大于 0")
        if heartbeat_interval_seconds <= 0:
            raise ValueError("heartbeat_interval_seconds 必须大于 0")
        if heartbeat_interval_seconds >= lease_seconds:
            raise ValueError("heartbeat_interval_seconds 必须小于 lease_seconds")
        if poll_interval_seconds <= 0:
            raise ValueError("poll_interval_seconds 必须大于 0")

        self._executor = executor
        self._policy = policy
        self._store = store
        self._worker_id = worker_id or f"worker_{uuid4().hex}"
        self._lease_seconds = lease_seconds
        self._heartbeat_interval_seconds = heartbeat_interval_seconds
        self._poll_interval_seconds = poll_interval_seconds
        self._recovery_decider = recovery_decider or fail_closed_recovery
        self._trace_sink = trace_sink or NullTraceSink()

    async def run(
        self,
        graph: ResolvedTaskGraph,
        *,
        trace_id: str | None = None,
    ) -> WorkflowRunResult:
        """Create a durable workflow and execute it."""
        resolved_trace_id = trace_id or new_trace_id()
        snapshot = await self._store.create_workflow(
            graph,
            deadline_at=time.time() + self._policy.workflow_timeout_seconds,
        )
        self._validate_snapshot_contract(snapshot)

        if snapshot.status in {
            WorkflowStatus.SUCCEEDED,
            WorkflowStatus.PARTIAL_SUCCESS,
            WorkflowStatus.FAILED,
            WorkflowStatus.CANCELLED,
        }:
            return self._result_from_snapshot(snapshot)

        await self._store.set_workflow_status(
            graph.workflow_id,
            WorkflowStatus.RUNNING,
        )
        return await self._drive(
            graph.workflow_id,
            trace_id=resolved_trace_id,
        )

    async def resume(
        self,
        workflow_id: str,
        *,
        trace_id: str | None = None,
    ) -> WorkflowRunResult:
        """
        Resume from durable state without re-running Planner or Validator.
        """
        resolved_trace_id = trace_id or new_trace_id()
        snapshot = await self._store.load_workflow(workflow_id)
        self._validate_snapshot_contract(snapshot)

        if snapshot.status in {
            WorkflowStatus.SUCCEEDED,
            WorkflowStatus.PARTIAL_SUCCESS,
            WorkflowStatus.FAILED,
            WorkflowStatus.CANCELLED,
        }:
            return self._result_from_snapshot(snapshot)

        if snapshot.deadline_at <= time.time():
            await self._timeout_workflow(workflow_id)
            return self._result_from_snapshot(
                await self._store.load_workflow(workflow_id)
            )

        await self._store.set_workflow_status(
            workflow_id,
            WorkflowStatus.RUNNING,
        )
        return await self._drive(
            workflow_id,
            trace_id=resolved_trace_id,
        )

    async def _drive(
        self,
        workflow_id: str,
        *,
        trace_id: str,
    ) -> WorkflowRunResult:
        running: dict[str, asyncio.Task[_LocalExecutionOutcome]] = {}

        try:
            while True:
                snapshot = await self._store.load_workflow(workflow_id)

                if snapshot.status == WorkflowStatus.CANCELLED:
                    await self._cancel_local(running)
                    return self._result_from_snapshot(snapshot)

                if time.time() >= snapshot.deadline_at:
                    await self._cancel_local(running)
                    await self._timeout_workflow(workflow_id)
                    return self._result_from_snapshot(
                        await self._store.load_workflow(workflow_id)
                    )

                await self._recover_expired(
                    snapshot,
                    trace_id=trace_id,
                )
                await self._advance_pending(
                    workflow_id,
                    trace_id=trace_id,
                )

                snapshot = await self._store.load_workflow(workflow_id)
                await self._launch_ready(
                    snapshot,
                    running,
                    trace_id=trace_id,
                )

                # Re-read because another worker may have completed tasks.
                snapshot = await self._store.load_workflow(workflow_id)
                if self._all_terminal(snapshot):
                    final_status = self._derive_workflow_status(snapshot)
                    await self._store.set_workflow_status(
                        workflow_id,
                        final_status,
                    )
                    return self._result_from_snapshot(
                        await self._store.load_workflow(workflow_id)
                    )

                if running:
                    done, _ = await asyncio.wait(
                        tuple(running.values()),
                        timeout=self._poll_interval_seconds,
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                    if done:
                        completed_ids = [
                            task_id
                            for task_id, future in running.items()
                            if future in done
                        ]
                        for task_id in completed_ids:
                            future = running.pop(task_id)
                            outcome = await self._consume_local_future(
                                workflow_id,
                                task_id,
                                future,
                                trace_id=trace_id,
                            )
                            if not outcome.lease_lost:
                                committed = await self._store.finish_task(
                                    workflow_id,
                                    task_id,
                                    worker_id=self._worker_id,
                                    result=outcome.result,
                                )
                                if committed is not None:
                                    await emit_trace(
                                        self._trace_sink,
                                        trace_id=trace_id,
                                        event_type=TraceEventType.TASK_FINISHED,
                                        workflow_id=workflow_id,
                                        task_id=task_id,
                                        parent_task_ids=committed.dependencies,
                                        agent_type=committed.agent_type,
                                        status=outcome.result.status.value,
                                        attributes={
                                            "attempt": committed.attempt,
                                            "worker_id": self._worker_id,
                                        },
                                    )
                else:
                    # No local coroutine may simply mean another worker owns the
                    # RUNNING tasks, or we are waiting for an expired lease.
                    await asyncio.sleep(self._poll_interval_seconds)

        except asyncio.CancelledError:
            await self._cancel_local(running)
            raise

    async def _advance_pending(
        self,
        workflow_id: str,
        *,
        trace_id: str,
    ) -> None:
        # Repeat until no more same-round propagation is possible. Example:
        # A FAILED -> B SKIPPED -> C SKIPPED.
        while True:
            snapshot = await self._store.load_workflow(workflow_id)
            changed = False

            for task_id in snapshot.topological_order:
                record = snapshot.tasks[task_id]
                task = record.task
                if task.status != TaskStatus.PENDING:
                    continue

                dependency_records = [
                    snapshot.tasks[dependency_id]
                    for dependency_id in task.dependencies
                ]

                blocked_by = [
                    dependency.task.task_id
                    for dependency in dependency_records
                    if dependency.task.status in _BLOCKING_DEPENDENCY_STATUSES
                ]

                if blocked_by:
                    result = TaskResult(
                        workflow_id=task.workflow_id,
                        task_id=task.task_id,
                        status=TaskStatus.SKIPPED,
                        summary="Task skipped because a dependency did not succeed",
                        data={"blocked_by": blocked_by},
                        trace_id=trace_id,
                    )
                    updated = await self._store.transition_task(
                        workflow_id,
                        task_id,
                        expected_statuses=(TaskStatus.PENDING,),
                        new_status=TaskStatus.SKIPPED,
                        result=result,
                    )
                    changed = changed or updated is not None
                    if updated is not None:
                        await emit_trace(
                            self._trace_sink,
                            trace_id=trace_id,
                            event_type=TraceEventType.TASK_SKIPPED,
                            workflow_id=workflow_id,
                            task_id=task_id,
                            parent_task_ids=task.dependencies,
                            agent_type=task.agent_type,
                            status=TaskStatus.SKIPPED.value,
                            attributes={"blocked_by": blocked_by},
                        )
                    continue

                if all(
                    dependency.task.status == TaskStatus.SUCCEEDED
                    for dependency in dependency_records
                ):
                    updated = await self._store.transition_task(
                        workflow_id,
                        task_id,
                        expected_statuses=(TaskStatus.PENDING,),
                        new_status=TaskStatus.READY,
                    )
                    changed = changed or updated is not None

            if not changed:
                return

    async def _launch_ready(
        self,
        snapshot: WorkflowSnapshot,
        running: dict[str, asyncio.Task[_LocalExecutionOutcome]],
        *,
        trace_id: str,
    ) -> None:
        # Local limit avoids creating excessive coroutines. Store claim enforces
        # the same limit globally across multiple scheduler processes.
        local_slots = self._policy.max_concurrency - len(running)
        if local_slots <= 0:
            return

        launched = 0
        for task_id in snapshot.topological_order:
            if launched >= local_slots:
                break
            if task_id in running:
                continue

            record = snapshot.tasks[task_id]
            if record.task.status != TaskStatus.READY:
                continue

            claimed = await self._store.claim_task(
                snapshot.workflow_id,
                task_id,
                worker_id=self._worker_id,
                lease_seconds=self._lease_seconds,
                max_concurrency=self._policy.max_concurrency,
            )
            if claimed is None:
                continue

            fresh = await self._store.load_workflow(snapshot.workflow_id)
            dependency_results = {
                dependency_id: fresh.tasks[dependency_id].result
                for dependency_id in claimed.dependencies
                if fresh.tasks[dependency_id].result is not None
            }

            await emit_trace(
                self._trace_sink,
                trace_id=trace_id,
                event_type=TraceEventType.TASK_CLAIMED,
                workflow_id=snapshot.workflow_id,
                task_id=task_id,
                parent_task_ids=claimed.dependencies,
                agent_type=claimed.agent_type,
                status=TaskStatus.RUNNING.value,
                attributes={
                    "attempt": claimed.attempt,
                    "worker_id": self._worker_id,
                },
            )

            running[task_id] = asyncio.create_task(
                self._execute_with_lease(
                    claimed,
                    dependency_results=dependency_results,
                    trace_id=trace_id,
                ),
                name=f"workflow:{snapshot.workflow_id}:task:{task_id}",
            )
            launched += 1

    async def _execute_with_lease(
        self,
        task: RuntimeTask,
        *,
        dependency_results: dict[str, TaskResult],
        trace_id: str,
    ) -> _LocalExecutionOutcome:
        execution = asyncio.create_task(
            self._executor.execute(
                task,
                dependency_results=dependency_results,
                trace_id=trace_id,
            )
        )
        heartbeat = asyncio.create_task(
            self._heartbeat_until_lost(task)
        )

        done, _ = await asyncio.wait(
            (execution, heartbeat),
            return_when=asyncio.FIRST_COMPLETED,
        )

        if heartbeat in done:
            try:
                lease_alive = heartbeat.result()
            except Exception:
                # If persistence/heartbeat itself becomes unavailable, this
                # worker can no longer prove ownership. Fail closed.
                lease_alive = False

            if not lease_alive:
                if not execution.done():
                    execution.cancel()
                await asyncio.gather(execution, return_exceptions=True)
                return _LocalExecutionOutcome(
                    result=TaskResult(
                        workflow_id=task.workflow_id,
                        task_id=task.task_id,
                        status=TaskStatus.CANCELLED,
                        summary="Local execution stopped after lease ownership was lost",
                        error=TaskError(
                            code="LEASE_LOST",
                            message=(
                                "Task lease expired, workflow was cancelled, or another "
                                "worker became authoritative"
                            ),
                            retryable=False,
                            ambiguous_side_effect=True,
                        ),
                        trace_id=trace_id,
                    ),
                    lease_lost=True,
                )

        if execution in done:
            heartbeat.cancel()
            await asyncio.gather(heartbeat, return_exceptions=True)
            result = await execution
            return _LocalExecutionOutcome(result=result)

        # Heartbeat can only finish with False; defensive fallback.
        heartbeat.cancel()
        await asyncio.gather(heartbeat, return_exceptions=True)
        result = await execution
        return _LocalExecutionOutcome(result=result)

    async def _heartbeat_until_lost(self, task: RuntimeTask) -> bool:
        while True:
            await asyncio.sleep(self._heartbeat_interval_seconds)
            ok = await self._store.heartbeat(
                task.workflow_id,
                task.task_id,
                worker_id=self._worker_id,
                lease_seconds=self._lease_seconds,
            )
            if not ok:
                return False

    async def _recover_expired(
        self,
        snapshot: WorkflowSnapshot,
        *,
        trace_id: str,
    ) -> None:
        now = time.time()
        for task_id, record in snapshot.tasks.items():
            if (
                record.task.status != TaskStatus.RUNNING
                or record.lease_until is None
                or record.lease_until > now
            ):
                continue

            action = self._recovery_decider(record.task)
            if action == RecoveryAction.RETRY:
                recovered = await self._store.recover_expired_task(
                    snapshot.workflow_id,
                    task_id,
                    retry=True,
                )
                if recovered is not None:
                    await emit_trace(
                        self._trace_sink,
                        trace_id=trace_id,
                        event_type=TraceEventType.TASK_RECOVERED,
                        workflow_id=snapshot.workflow_id,
                        task_id=task_id,
                        parent_task_ids=recovered.dependencies,
                        agent_type=recovered.agent_type,
                        status=recovered.status.value,
                        attributes={"recovery_action": RecoveryAction.RETRY.value},
                    )
                continue

            failure = TaskResult(
                workflow_id=record.task.workflow_id,
                task_id=record.task.task_id,
                status=TaskStatus.FAILED,
                summary="Previous worker disappeared while task execution was in-flight",
                error=TaskError(
                    code="ORPHANED_EXECUTION_UNKNOWN",
                    message=(
                        "RUNNING task lease expired. Runtime cannot prove whether "
                        "external side effects happened, so automatic replay is disabled."
                    ),
                    retryable=False,
                    ambiguous_side_effect=True,
                ),
                trace_id=trace_id,
            )
            recovered = await self._store.recover_expired_task(
                snapshot.workflow_id,
                task_id,
                retry=False,
                failure_result=failure,
            )
            if recovered is not None:
                await emit_trace(
                    self._trace_sink,
                    trace_id=trace_id,
                    event_type=TraceEventType.TASK_RECOVERED,
                    workflow_id=snapshot.workflow_id,
                    task_id=task_id,
                    parent_task_ids=recovered.dependencies,
                    agent_type=recovered.agent_type,
                    status=recovered.status.value,
                    attributes={
                        "recovery_action": RecoveryAction.FAIL_CLOSED.value
                    },
                )

    async def _consume_local_future(
        self,
        workflow_id: str,
        task_id: str,
        future: asyncio.Task[_LocalExecutionOutcome],
        *,
        trace_id: str,
    ) -> _LocalExecutionOutcome:
        try:
            outcome = future.result()
        except asyncio.CancelledError:
            return _LocalExecutionOutcome(
                result=TaskResult(
                    workflow_id=workflow_id,
                    task_id=task_id,
                    status=TaskStatus.CANCELLED,
                    summary="Task execution was cancelled",
                    error=TaskError(
                        code="TASK_CANCELLED",
                        message="Scheduler observed a cancelled local execution",
                        retryable=False,
                        ambiguous_side_effect=True,
                    ),
                    trace_id=trace_id,
                )
            )
        except Exception as exc:
            return _LocalExecutionOutcome(
                result=TaskResult(
                    workflow_id=workflow_id,
                    task_id=task_id,
                    status=TaskStatus.FAILED,
                    summary="Executor raised outside its normal TaskResult contract",
                    error=TaskError(
                        code="SCHEDULER_EXECUTOR_ERROR",
                        message=f"{type(exc).__name__}: {exc}",
                        retryable=False,
                        ambiguous_side_effect=False,
                    ),
                    trace_id=trace_id,
                )
            )

        if (
            outcome.result.workflow_id != workflow_id
            or outcome.result.task_id != task_id
        ):
            return _LocalExecutionOutcome(
                result=TaskResult(
                    workflow_id=workflow_id,
                    task_id=task_id,
                    status=TaskStatus.FAILED,
                    summary="Executor returned a mismatched result",
                    error=TaskError(
                        code="TASK_RESULT_ID_MISMATCH",
                        message=(
                            "Executor result identity does not match claimed RuntimeTask"
                        ),
                        retryable=False,
                        ambiguous_side_effect=False,
                    ),
                    trace_id=trace_id,
                )
            )

        if outcome.result.trace_id is None:
            outcome = _LocalExecutionOutcome(
                result=outcome.result.model_copy(
                    update={"trace_id": trace_id}
                ),
                lease_lost=outcome.lease_lost,
            )

        return outcome

    async def _timeout_workflow(self, workflow_id: str) -> None:
        await self._store.cancel_nonterminal_tasks(
            workflow_id,
            code="WORKFLOW_TIMEOUT",
            message=(
                "Workflow exceeded durable deadline; in-flight side effects may be ambiguous"
            ),
        )

    @staticmethod
    async def _cancel_local(
        running: dict[str, asyncio.Task[_LocalExecutionOutcome]],
    ) -> None:
        for future in running.values():
            future.cancel()
        if running:
            await asyncio.gather(*running.values(), return_exceptions=True)
        running.clear()

    @staticmethod
    def _all_terminal(snapshot: WorkflowSnapshot) -> bool:
        return all(
            record.task.status in _TERMINAL_TASK_STATUSES
            for record in snapshot.tasks.values()
        )

    @staticmethod
    def _derive_workflow_status(snapshot: WorkflowSnapshot) -> WorkflowStatus:
        records = list(snapshot.tasks.values())

        if all(
            record.task.status == TaskStatus.SUCCEEDED
            for record in records
        ):
            return WorkflowStatus.SUCCEEDED

        if any(
            record.task.required
            and record.task.status != TaskStatus.SUCCEEDED
            for record in records
        ):
            return WorkflowStatus.FAILED

        return WorkflowStatus.PARTIAL_SUCCESS

    @staticmethod
    def _result_from_snapshot(snapshot: WorkflowSnapshot) -> WorkflowRunResult:
        return WorkflowRunResult(
            workflow_id=snapshot.workflow_id,
            status=snapshot.status,
            task_results=snapshot.task_results,
            task_states=snapshot.task_states,
        )

    @staticmethod
    def _validate_snapshot_contract(snapshot: WorkflowSnapshot) -> None:
        if set(snapshot.topological_order) != set(snapshot.tasks):
            raise SchedulerInvariantError(
                "Persisted topological_order 与 Task 集合不一致"
            )
        for task_id, record in snapshot.tasks.items():
            if record.task.task_id != task_id:
                raise SchedulerInvariantError("Persisted task_id key mismatch")
            if record.task.workflow_id != snapshot.workflow_id:
                raise SchedulerInvariantError(
                    f"Task {task_id} workflow_id 与持久化 Workflow 不一致"
                )
