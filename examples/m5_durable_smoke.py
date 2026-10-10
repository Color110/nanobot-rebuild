from __future__ import annotations

import asyncio
import time
from pathlib import Path

from app.orchestration import (
    AgentSpec,
    OrchestrationPolicy,
    PlannedTask,
    RecoveryAction,
    SQLiteTaskStore,
    TaskPlan,
    TaskPlanValidator,
    TaskResult,
    TaskScheduler,
    TaskStatus,
    WorkflowStatus,
)


class FakeExecutor:
    def __init__(self, *, delay: float = 0.05) -> None:
        self.delay = delay
        self.started: list[tuple[str, int]] = []

    async def execute(
        self,
        task,
        *,
        dependency_results=None,
        trace_id=None,
    ) -> TaskResult:
        self.started.append((task.task_id, task.attempt))
        await asyncio.sleep(self.delay)
        return TaskResult(
            workflow_id=task.workflow_id,
            task_id=task.task_id,
            status=TaskStatus.SUCCEEDED,
            summary=f"{task.task_id} completed",
            data={
                "dependency_ids": sorted((dependency_results or {}).keys())
            },
        )


def build_graph(
    workflow_id: str,
    policy: OrchestrationPolicy,
):
    agent_specs = {
        "researcher": AgentSpec(
            agent_type="researcher",
            system_prompt="负责资料调研。",
        ),
        "writer": AgentSpec(
            agent_type="writer",
            system_prompt="负责撰写报告。",
        ),
    }

    plan = TaskPlan(
        tasks=(
            PlannedTask(
                task_id="research_product",
                objective="调查产品信息",
                agent_type="researcher",
            ),
            PlannedTask(
                task_id="research_funding",
                objective="调查融资信息",
                agent_type="researcher",
            ),
            PlannedTask(
                task_id="write_report",
                objective="汇总调研结果并撰写报告",
                agent_type="writer",
                dependencies=(
                    "research_product",
                    "research_funding",
                ),
            ),
        )
    )

    return TaskPlanValidator(
        agent_specs=agent_specs,
        policy=policy,
    ).validate_and_resolve(
        plan,
        workflow_id=workflow_id,
    )


async def normal_run_and_restart(
    db_path: Path,
    policy: OrchestrationPolicy,
) -> None:
    print("\n=== SCENARIO 1: durable run + restart ===")

    executor = FakeExecutor()
    scheduler = TaskScheduler(
        executor=executor,
        policy=policy,
        store=SQLiteTaskStore(db_path),
        lease_seconds=1.0,
        heartbeat_interval_seconds=0.2,
        poll_interval_seconds=0.02,
    )

    result = await scheduler.run(
        build_graph("wf_durable_ok", policy)
    )

    assert result.status == WorkflowStatus.SUCCEEDED
    assert result.task_states["write_report"].status == TaskStatus.SUCCEEDED
    assert executor.started == [
        ("research_funding", 1),
        ("research_product", 1),
        ("write_report", 1),
    ] or executor.started == [
        ("research_product", 1),
        ("research_funding", 1),
        ("write_report", 1),
    ]

    # 模拟“进程完全重启”：重新创建 Store / Executor / Scheduler。
    new_executor = FakeExecutor()
    new_scheduler = TaskScheduler(
        executor=new_executor,
        policy=policy,
        store=SQLiteTaskStore(db_path),
        lease_seconds=1.0,
        heartbeat_interval_seconds=0.2,
        poll_interval_seconds=0.02,
    )

    resumed = await new_scheduler.resume("wf_durable_ok")

    assert resumed.status == WorkflowStatus.SUCCEEDED
    assert new_executor.started == []

    print("PASS: completed tasks were loaded from durable state and not replayed")


async def create_orphaned_task(
    *,
    store: SQLiteTaskStore,
    graph,
    policy: OrchestrationPolicy,
) -> None:
    await store.create_workflow(
        graph,
        deadline_at=time.time() + 10.0,
    )
    await store.set_workflow_status(
        graph.workflow_id,
        WorkflowStatus.RUNNING,
    )

    root_task = graph.topological_order[0]

    await store.transition_task(
        graph.workflow_id,
        root_task,
        expected_statuses=(TaskStatus.PENDING,),
        new_status=TaskStatus.READY,
    )

    claimed = await store.claim_task(
        graph.workflow_id,
        root_task,
        worker_id="dead_worker",
        lease_seconds=0.1,
        max_concurrency=policy.max_concurrency,
    )
    assert claimed is not None
    assert claimed.status == TaskStatus.RUNNING
    assert claimed.attempt == 1

    # 模拟 worker 崩溃且不再 heartbeat。
    await asyncio.sleep(0.15)


async def fail_closed_recovery(
    db_path: Path,
    policy: OrchestrationPolicy,
) -> None:
    print("\n=== SCENARIO 2: orphaned RUNNING -> fail closed ===")

    graph = build_graph("wf_orphan_fail_closed", policy)
    store = SQLiteTaskStore(db_path)

    await create_orphaned_task(
        store=store,
        graph=graph,
        policy=policy,
    )

    executor = FakeExecutor()
    scheduler = TaskScheduler(
        executor=executor,
        policy=policy,
        store=SQLiteTaskStore(db_path),
        lease_seconds=1.0,
        heartbeat_interval_seconds=0.2,
        poll_interval_seconds=0.02,
    )

    result = await scheduler.resume(graph.workflow_id)

    orphan_task = graph.topological_order[0]
    assert result.task_states[orphan_task].status == TaskStatus.FAILED
    assert result.status == WorkflowStatus.FAILED

    print("PASS: expired RUNNING task was not blindly replayed")


async def safe_retry_recovery(
    db_path: Path,
    policy: OrchestrationPolicy,
) -> None:
    print("\n=== SCENARIO 3: explicitly safe orphan retry ===")

    graph = build_graph("wf_orphan_safe_retry", policy)
    store = SQLiteTaskStore(db_path)

    await create_orphaned_task(
        store=store,
        graph=graph,
        policy=policy,
    )

    executor = FakeExecutor()
    scheduler = TaskScheduler(
        executor=executor,
        policy=policy,
        store=SQLiteTaskStore(db_path),
        lease_seconds=1.0,
        heartbeat_interval_seconds=0.2,
        poll_interval_seconds=0.02,
        recovery_decider=lambda task: RecoveryAction.RETRY,
    )

    result = await scheduler.resume(graph.workflow_id)

    orphan_task = graph.topological_order[0]
    assert result.status == WorkflowStatus.SUCCEEDED
    assert result.task_states[orphan_task].attempt == 2
    assert (orphan_task, 2) in executor.started

    print("PASS: safe recovery retried with attempt incremented to 2")


async def main() -> None:
    db_path = Path("runtime/m5-smoke.sqlite3")
    db_path.parent.mkdir(parents=True, exist_ok=True)

    for suffix in ("", "-wal", "-shm"):
        candidate = Path(str(db_path) + suffix)
        if candidate.exists():
            candidate.unlink()

    policy = OrchestrationPolicy(
        max_tasks=8,
        max_depth=4,
        max_concurrency=2,
        workflow_timeout_seconds=10.0,
    )

    await normal_run_and_restart(db_path, policy)
    await fail_closed_recovery(db_path, policy)
    await safe_retry_recovery(db_path, policy)

    print("\n=== M5 DURABLE SMOKE PASSED ===")


if __name__ == "__main__":
    asyncio.run(main())
