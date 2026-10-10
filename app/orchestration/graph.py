from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from app.orchestration.models import (
    AgentSpec,
    RuntimeTask,
    TaskPlan,
)
from app.orchestration.policy import OrchestrationPolicy


class TaskPlanValidationError(ValueError):
    """Planner output violates deterministic Runtime constraints."""


@dataclass(frozen=True)
class ResolvedTaskGraph:
    workflow_id: str
    tasks: tuple[RuntimeTask, ...]
    topological_order: tuple[str, ...]
    depth_by_task: dict[str, int]

    @property
    def by_id(self) -> dict[str, RuntimeTask]:
        return {task.task_id: task for task in self.tasks}


class TaskPlanValidator:
    """
    Trust boundary between probabilistic Planner and deterministic Runtime.

    Planner proposes. Runtime validates and grants.
    """

    def __init__(
        self,
        *,
        agent_specs: dict[str, AgentSpec],
        policy: OrchestrationPolicy,
    ) -> None:
        self._agent_specs = dict(agent_specs)
        self._policy = policy

    def validate_and_resolve(
        self,
        plan: TaskPlan,
        *,
        workflow_id: str | None = None,
    ) -> ResolvedTaskGraph:
        if len(plan.tasks) > self._policy.max_tasks:
            raise TaskPlanValidationError(
                f"Task 数量超过限制: {len(plan.tasks)} > {self._policy.max_tasks}"
            )

        task_ids = [task.task_id for task in plan.tasks]
        if len(set(task_ids)) != len(task_ids):
            raise TaskPlanValidationError("Task ID 必须唯一")

        task_id_set = set(task_ids)

        for task in plan.tasks:
            missing = [dep for dep in task.dependencies if dep not in task_id_set]
            if missing:
                raise TaskPlanValidationError(
                    f"Task {task.task_id} 依赖未知 Task: {', '.join(missing)}"
                )

            spec = self._agent_specs.get(task.agent_type)
            if spec is None:
                raise TaskPlanValidationError(
                    f"Task {task.task_id} 使用未知 agent_type: {task.agent_type}"
                )

            requested = set(task.requested_tools)
            unauthorized = requested - set(spec.allowed_tools)
            if unauthorized:
                raise TaskPlanValidationError(
                    f"Task {task.task_id} 请求未授权 Tool: "
                    + ", ".join(sorted(unauthorized))
                )

        topological_order = self._topological_sort(plan)
        depth_by_task = self._compute_depths(plan, topological_order)

        actual_max_depth = max(depth_by_task.values(), default=0)
        if actual_max_depth > self._policy.max_depth:
            raise TaskPlanValidationError(
                f"Task Graph 深度超过限制: "
                f"{actual_max_depth} > {self._policy.max_depth}"
            )

        resolved_workflow_id = workflow_id or f"wf_{uuid4().hex}"

        runtime_tasks: list[RuntimeTask] = []
        for task in plan.tasks:
            spec = self._agent_specs[task.agent_type]
            runtime_tasks.append(
                RuntimeTask(
                    workflow_id=resolved_workflow_id,
                    task_id=task.task_id,
                    objective=task.objective,
                    agent_type=task.agent_type,
                    dependencies=task.dependencies,
                    granted_tools=tuple(task.requested_tools),
                    required=task.required,
                    input_data=task.input_data,
                    budget=spec.budget,
                )
            )

        return ResolvedTaskGraph(
            workflow_id=resolved_workflow_id,
            tasks=tuple(runtime_tasks),
            topological_order=topological_order,
            depth_by_task=depth_by_task,
        )

    @staticmethod
    def _topological_sort(plan: TaskPlan) -> tuple[str, ...]:
        indegree = {task.task_id: len(task.dependencies) for task in plan.tasks}
        dependents: dict[str, list[str]] = {task.task_id: [] for task in plan.tasks}

        for task in plan.tasks:
            for dependency in task.dependencies:
                dependents[dependency].append(task.task_id)

        ready = sorted(task_id for task_id, degree in indegree.items() if degree == 0)
        order: list[str] = []

        while ready:
            current = ready.pop(0)
            order.append(current)

            for child in sorted(dependents[current]):
                indegree[child] -= 1
                if indegree[child] == 0:
                    ready.append(child)
                    ready.sort()

        if len(order) != len(plan.tasks):
            raise TaskPlanValidationError("Task Graph 存在循环依赖")

        return tuple(order)

    @staticmethod
    def _compute_depths(
        plan: TaskPlan,
        topological_order: tuple[str, ...],
    ) -> dict[str, int]:
        by_id = {task.task_id: task for task in plan.tasks}
        depths: dict[str, int] = {}

        for task_id in topological_order:
            task = by_id[task_id]
            if not task.dependencies:
                depths[task_id] = 1
            else:
                depths[task_id] = 1 + max(depths[dep] for dep in task.dependencies)

        return depths
