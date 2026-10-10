import pytest

from app.orchestration.graph import (
    TaskPlanValidationError,
    TaskPlanValidator,
)
from app.orchestration.models import AgentSpec, PlannedTask, TaskPlan
from app.orchestration.policy import OrchestrationPolicy


def _validator(*, max_depth: int = 4) -> TaskPlanValidator:
    specs = {
        "researcher": AgentSpec(
            agent_type="researcher",
            system_prompt="Research carefully.",
            allowed_tools=frozenset({"retrieve_knowledge", "search_web"}),
        ),
        "writer": AgentSpec(
            agent_type="writer",
            system_prompt="Write from supplied evidence only.",
            allowed_tools=frozenset(),
        ),
    }
    return TaskPlanValidator(
        agent_specs=specs,
        policy=OrchestrationPolicy(
            max_tasks=8,
            max_depth=max_depth,
            max_concurrency=4,
        ),
    )


def test_valid_dag_is_resolved_into_runtime_tasks() -> None:
    plan = TaskPlan(
        tasks=(
            PlannedTask(
                task_id="research",
                objective="collect evidence",
                agent_type="researcher",
                requested_tools=("retrieve_knowledge",),
            ),
            PlannedTask(
                task_id="write",
                objective="write final report",
                agent_type="writer",
                dependencies=("research",),
            ),
        )
    )

    graph = _validator().validate_and_resolve(plan, workflow_id="wf_test")

    assert graph.workflow_id == "wf_test"
    assert graph.topological_order == ("research", "write")
    assert graph.depth_by_task == {"research": 1, "write": 2}
    assert graph.by_id["research"].granted_tools == ("retrieve_knowledge",)


def test_cycle_is_rejected() -> None:
    plan = TaskPlan(
        tasks=(
            PlannedTask(
                task_id="a",
                objective="A",
                agent_type="writer",
                dependencies=("b",),
            ),
            PlannedTask(
                task_id="b",
                objective="B",
                agent_type="writer",
                dependencies=("a",),
            ),
        )
    )

    with pytest.raises(TaskPlanValidationError, match="循环依赖"):
        _validator().validate_and_resolve(plan)


def test_unknown_dependency_is_rejected() -> None:
    plan = TaskPlan(
        tasks=(
            PlannedTask(
                task_id="a",
                objective="A",
                agent_type="writer",
                dependencies=("missing",),
            ),
        )
    )

    with pytest.raises(TaskPlanValidationError, match="未知 Task"):
        _validator().validate_and_resolve(plan)


def test_planner_cannot_grant_unauthorized_tool() -> None:
    plan = TaskPlan(
        tasks=(
            PlannedTask(
                task_id="write",
                objective="write report",
                agent_type="writer",
                requested_tools=("search_web",),
            ),
        )
    )

    with pytest.raises(TaskPlanValidationError, match="未授权 Tool"):
        _validator().validate_and_resolve(plan)


def test_graph_depth_is_bounded_by_runtime_policy() -> None:
    plan = TaskPlan(
        tasks=(
            PlannedTask(task_id="a", objective="A", agent_type="writer"),
            PlannedTask(
                task_id="b",
                objective="B",
                agent_type="writer",
                dependencies=("a",),
            ),
            PlannedTask(
                task_id="c",
                objective="C",
                agent_type="writer",
                dependencies=("b",),
            ),
        )
    )

    with pytest.raises(TaskPlanValidationError, match="深度超过限制"):
        _validator(max_depth=2).validate_and_resolve(plan)
