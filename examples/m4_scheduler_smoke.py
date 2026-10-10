from __future__ import annotations

import asyncio
from time import perf_counter

from app.orchestration import (
    AgentSpec,
    OrchestrationPolicy,
    PlannedTask,
    TaskPlan,
    TaskPlanValidator,
    TaskResult,
    TaskScheduler,
    TaskStatus,
    WorkflowStatus,
)
from app.orchestration.models import (
    RuntimeTask,
    TaskError,
)


class FakeSubAgentExecutor:
    """
    M4 冒烟测试专用 Executor。

    不调用真实 LLM，也不调用 AgentRunner。

    目的只是模拟：
    - Task 执行耗时
    - Task 成功
    - 指定 Task 失败
    - Scheduler 传入 dependency_results
    - 当前并发数 / 最大并发数
    """

    def __init__(
        self,
        *,
        delays: dict[str, float] | None = None,
        fail_tasks: set[str] | None = None,
    ) -> None:
        self.delays = delays or {}
        self.fail_tasks = fail_tasks or set()

        self.active_count = 0
        self.max_active_count = 0

        self.started_tasks: list[str] = []
        self.finished_tasks: list[str] = []

        self.events: list[str] = []

    async def execute(
        self,
        task: RuntimeTask,
        *,
        dependency_results: dict[str, TaskResult] | None = None,
        trace_id: str | None = None,
    ) -> TaskResult:
        dependency_results = dependency_results or {}

        self.active_count += 1
        self.max_active_count = max(
            self.max_active_count,
            self.active_count,
        )

        self.started_tasks.append(task.task_id)

        dependency_ids = list(dependency_results.keys())

        self.events.append(
            f"START  task={task.task_id:<18} "
            f"active={self.active_count} "
            f"dependencies={dependency_ids}"
        )

        try:
            await asyncio.sleep(
                self.delays.get(task.task_id, 0.05)
            )

            if task.task_id in self.fail_tasks:
                self.events.append(
                    f"FAILED task={task.task_id:<18}"
                )

                return TaskResult(
                    workflow_id=task.workflow_id,
                    task_id=task.task_id,
                    status=TaskStatus.FAILED,
                    summary=f"{task.task_id} simulated failure",
                    error=TaskError(
                        code="SMOKE_TEST_FAILURE",
                        message=(
                            f"模拟 Task {task.task_id} 执行失败"
                        ),
                        retryable=False,
                        ambiguous_side_effect=False,
                    ),
                )

            self.events.append(
                f"SUCCESS task={task.task_id:<17}"
            )

            return TaskResult(
                workflow_id=task.workflow_id,
                task_id=task.task_id,
                status=TaskStatus.SUCCEEDED,
                summary=f"{task.task_id} completed",
                data={
                    "task_id": task.task_id,
                    "dependency_ids": dependency_ids,
                    "mock_result": (
                        f"result-from-{task.task_id}"
                    ),
                },
            )

        finally:
            self.active_count -= 1
            self.finished_tasks.append(task.task_id)


def build_graph(
    *,
    workflow_id: str,
    policy: OrchestrationPolicy,
):
    """
    构造：

        research_product ───┐
                            ├──→ write_report
        research_funding ───┘

    前两个任务没有依赖，因此应该并行执行。

    write_report 必须等两个研究任务都成功后才能执行。
    """

    agent_specs = {
        "researcher": AgentSpec(
            agent_type="researcher",
            system_prompt="负责资料调研。",
            allowed_tools=frozenset(),
        ),
        "writer": AgentSpec(
            agent_type="writer",
            system_prompt="负责根据已有研究结果撰写报告。",
            allowed_tools=frozenset(),
        ),
    }

    plan = TaskPlan(
        tasks=(
            PlannedTask(
                task_id="research_product",
                objective="调查目标公司的产品情况",
                agent_type="researcher",
                dependencies=(),
                requested_tools=(),
                required=True,
            ),
            PlannedTask(
                task_id="research_funding",
                objective="调查目标公司的融资情况",
                agent_type="researcher",
                dependencies=(),
                requested_tools=(),
                required=True,
            ),
            PlannedTask(
                task_id="write_report",
                objective="根据产品和融资调研结果撰写报告",
                agent_type="writer",
                dependencies=(
                    "research_product",
                    "research_funding",
                ),
                requested_tools=(),
                required=True,
            ),
        )
    )

    validator = TaskPlanValidator(
        agent_specs=agent_specs,
        policy=policy,
    )

    return validator.validate_and_resolve(
        plan,
        workflow_id=workflow_id,
    )


def print_events(
    executor: FakeSubAgentExecutor,
) -> None:
    print()

    for event in executor.events:
        print(f"  {event}")


def print_task_states(result) -> None:
    print()

    for task_id, task in result.task_states.items():
        task_result = result.task_results.get(task_id)

        print(
            f"  {task_id:<18} "
            f"status={task.status.value:<10} "
            f"attempt={task.attempt} "
            f"summary="
            f"{task_result.summary if task_result else '-'}"
        )


async def smoke_success() -> None:
    print()
    print("=" * 72)
    print("SCENARIO 1: 正常 DAG + max_concurrency=2")
    print("=" * 72)

    policy = OrchestrationPolicy(
        max_tasks=8,
        max_depth=4,
        max_concurrency=2,
        workflow_timeout_seconds=10.0,
    )

    graph = build_graph(
        workflow_id="wf_m4_success",
        policy=policy,
    )

    executor = FakeSubAgentExecutor(
        delays={
            "research_product": 0.30,
            "research_funding": 0.30,
            "write_report": 0.10,
        }
    )

    scheduler = TaskScheduler(
        executor=executor,
        policy=policy,
    )

    started = perf_counter()

    result = await scheduler.run(graph)

    elapsed = perf_counter() - started

    print()
    print("Execution events:")
    print_events(executor)

    print()
    print("Final task states:")
    print_task_states(result)

    print()
    print(f"workflow_status = {result.status.value}")
    print(
        f"max_active_count = "
        f"{executor.max_active_count}"
    )
    print(f"elapsed = {elapsed:.3f}s")

    # ------------------------------------------------------------
    # 核心断言 1：
    # 两个 research Task 必须都执行。
    # ------------------------------------------------------------

    assert "research_product" in executor.started_tasks
    assert "research_funding" in executor.started_tasks
    assert "write_report" in executor.started_tasks

    # ------------------------------------------------------------
    # 核心断言 2：
    # max_concurrency=2，所以两个独立 research Task
    # 应该真正同时进入 RUNNING。
    # ------------------------------------------------------------

    assert executor.max_active_count == 2

    # ------------------------------------------------------------
    # 核心断言 3：
    # 三个 Task 最终全部 SUCCEEDED。
    # ------------------------------------------------------------

    assert (
        result.task_states["research_product"].status
        == TaskStatus.SUCCEEDED
    )

    assert (
        result.task_states["research_funding"].status
        == TaskStatus.SUCCEEDED
    )

    assert (
        result.task_states["write_report"].status
        == TaskStatus.SUCCEEDED
    )

    # ------------------------------------------------------------
    # 核心断言 4：
    # Workflow 整体成功。
    # ------------------------------------------------------------

    assert result.status == WorkflowStatus.SUCCEEDED

    # ------------------------------------------------------------
    # 核心断言 5：
    # Scheduler 必须把两个 dependency 的 TaskResult
    # 传给 write_report。
    # ------------------------------------------------------------

    write_result = result.task_results["write_report"]

    assert set(
        write_result.data["dependency_ids"]
    ) == {
        "research_product",
        "research_funding",
    }

    # ------------------------------------------------------------
    # 一个简单的时间侧验证。
    #
    # 两个 research 各 0.30 秒，
    # 如果串行执行至少需要：
    #
    # 0.30 + 0.30 + 0.10 ≈ 0.70 秒
    #
    # 如果前两个真正并行：
    #
    # max(0.30, 0.30) + 0.10 ≈ 0.40 秒
    #
    # 留一点机器调度余量。
    # ------------------------------------------------------------

    assert elapsed < 0.65

    print()
    print("SCENARIO 1 PASSED")


async def smoke_failure_propagation() -> None:
    print()
    print("=" * 72)
    print(
        "SCENARIO 2: 上游失败 → 下游 SKIPPED"
    )
    print("=" * 72)

    policy = OrchestrationPolicy(
        max_tasks=8,
        max_depth=4,
        max_concurrency=2,
        workflow_timeout_seconds=10.0,
    )

    graph = build_graph(
        workflow_id="wf_m4_failure",
        policy=policy,
    )

    executor = FakeSubAgentExecutor(
        delays={
            "research_product": 0.20,
            "research_funding": 0.20,
            "write_report": 0.10,
        },
        fail_tasks={
            "research_funding",
        },
    )

    scheduler = TaskScheduler(
        executor=executor,
        policy=policy,
    )

    result = await scheduler.run(graph)

    print()
    print("Execution events:")
    print_events(executor)

    print()
    print("Final task states:")
    print_task_states(result)

    print()
    print(f"workflow_status = {result.status.value}")
    print(
        f"max_active_count = "
        f"{executor.max_active_count}"
    )

    # ------------------------------------------------------------
    # research_product 正常成功。
    # ------------------------------------------------------------

    assert (
        result.task_states["research_product"].status
        == TaskStatus.SUCCEEDED
    )

    # ------------------------------------------------------------
    # research_funding 是我们故意模拟失败的 Task。
    # ------------------------------------------------------------

    assert (
        result.task_states["research_funding"].status
        == TaskStatus.FAILED
    )

    # ------------------------------------------------------------
    # write_report 依赖：
    #
    # research_product
    # research_funding
    #
    # funding FAILED，所以 write_report 不应该执行。
    #
    # 它应该：
    #
    # PENDING → SKIPPED
    # ------------------------------------------------------------

    assert (
        result.task_states["write_report"].status
        == TaskStatus.SKIPPED
    )

    # 最重要的一条：
    # write_report 根本不应该进入 Executor。
    assert "write_report" not in executor.started_tasks

    # ------------------------------------------------------------
    # 检查 SKIPPED 原因。
    # ------------------------------------------------------------

    skipped_result = result.task_results[
        "write_report"
    ]

    assert skipped_result.status == TaskStatus.SKIPPED

    assert (
        "research_funding"
        in skipped_result.data["blocked_by"]
    )

    # ------------------------------------------------------------
    # write_report 是 required=True，
    # 所以 Required Task 没成功时，
    # Workflow 整体应该 FAILED。
    # ------------------------------------------------------------

    assert result.status == WorkflowStatus.FAILED

    print()
    print("SCENARIO 2 PASSED")


async def main() -> None:
    await smoke_success()
    await smoke_failure_propagation()

    print()
    print("=" * 72)
    print("M4 SCHEDULER SMOKE TEST PASSED")
    print("=" * 72)

    print(
        "Validated: "
        "DAG dependency + bounded concurrency + "
        "state transition + failure propagation"
    )


if __name__ == "__main__":
    asyncio.run(main())