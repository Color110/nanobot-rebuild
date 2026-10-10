from __future__ import annotations

from app.execution_mode import ExecutionMode

from .models import (
    EvalCase,
    EvalDimension,
    EvalRunResult,
    FailureCategory,
    GradeResult,
)


def grade_run(case: EvalCase, run: EvalRunResult) -> tuple[GradeResult, ...]:
    grades: list[GradeResult] = []

    grades.append(GradeResult(
        name="execution",
        dimension=EvalDimension.RELIABILITY,
        passed=run.execution_succeeded,
        score=1.0 if run.execution_succeeded else 0.0,
        reason=(
            "execution completed"
            if run.execution_succeeded
            else (run.error_message or "execution failed")
        ),
        failure_category=(
            FailureCategory.NONE
            if run.execution_succeeded
            else run.failure_category
        ),
    ))

    if case.expected_tools:
        actual = set(run.tool_names)
        missing = [name for name in case.expected_tools if name not in actual]
        grades.append(GradeResult(
            name="required_tools",
            dimension=EvalDimension.RELIABILITY,
            passed=not missing,
            score=1.0 if not missing else 0.0,
            reason=(
                "all required tools were called"
                if not missing
                else f"missing tools: {', '.join(missing)}"
            ),
            failure_category=(
                FailureCategory.NONE if not missing else FailureCategory.TOOL_CALLING
            ),
        ))

    if case.required_successful_tools:
        successful = set(run.successful_tool_names)
        missing = [
            name
            for name in case.required_successful_tools
            if name not in successful
        ]
        grades.append(GradeResult(
            name="successful_tools",
            dimension=EvalDimension.RELIABILITY,
            passed=not missing,
            score=1.0 if not missing else 0.0,
            reason=(
                "all required tools completed successfully"
                if not missing
                else f"required tools never succeeded: {', '.join(missing)}"
            ),
            failure_category=(
                FailureCategory.NONE if not missing else FailureCategory.TOOL_EXECUTION
            ),
        ))

    if case.forbidden_tools:
        actual = set(run.tool_names)
        used = [name for name in case.forbidden_tools if name in actual]
        grades.append(GradeResult(
            name="forbidden_tools",
            dimension=EvalDimension.RELIABILITY,
            passed=not used,
            score=1.0 if not used else 0.0,
            reason=(
                "no forbidden tool was called"
                if not used
                else f"forbidden tools used: {', '.join(used)}"
            ),
            failure_category=(
                FailureCategory.NONE if not used else FailureCategory.TOOL_CALLING
            ),
        ))

    if case.required_text:
        lowered = run.final_content.lower()
        missing = [
            text
            for text in case.required_text
            if text.lower() not in lowered
        ]
        grades.append(GradeResult(
            name="required_text",
            dimension=EvalDimension.CORRECTNESS,
            passed=not missing,
            score=1.0 if not missing else 0.0,
            reason=(
                "all required text present"
                if not missing
                else f"missing text: {missing}"
            ),
            failure_category=(
                FailureCategory.NONE if not missing else FailureCategory.MODEL_OUTPUT
            ),
        ))

    if run.mode == ExecutionMode.ORCHESTRATED:
        allowed = set(case.allowed_workflow_statuses)
        ok = run.workflow_status in allowed
        grades.append(GradeResult(
            name="workflow_status",
            dimension=EvalDimension.RELIABILITY,
            passed=ok,
            score=1.0 if ok else 0.0,
            reason=(
                f"status={run.workflow_status}"
                if ok
                else (
                    f"unexpected status={run.workflow_status}; "
                    f"allowed={[x.value for x in allowed]}"
                )
            ),
            failure_category=(
                FailureCategory.NONE
                if ok
                else (
                    run.failure_category
                    if run.failure_category != FailureCategory.NONE
                    else FailureCategory.RUNTIME
                )
            ),
        ))

    if case.min_task_success_rate is not None and run.mode == ExecutionMode.ORCHESTRATED:
        rate = run.task_success_rate or 0.0
        ok = rate >= case.min_task_success_rate
        grades.append(GradeResult(
            name="task_success_rate",
            dimension=EvalDimension.RELIABILITY,
            passed=ok,
            score=1.0 if ok else rate,
            reason=(
                f"task_success_rate={rate:.3f}, "
                f"required>={case.min_task_success_rate:.3f}"
            ),
            failure_category=(
                FailureCategory.NONE if ok else FailureCategory.RUNTIME
            ),
        ))

    if case.max_tool_errors is not None:
        ok = run.tool_error_count <= case.max_tool_errors
        grades.append(GradeResult(
            name="tool_error_budget",
            dimension=EvalDimension.RELIABILITY,
            passed=ok,
            score=1.0 if ok else 0.0,
            reason=(
                f"tool_errors={run.tool_error_count} <= {case.max_tool_errors}"
                if ok
                else f"tool_errors={run.tool_error_count} > {case.max_tool_errors}"
            ),
            failure_category=(
                FailureCategory.NONE if ok else FailureCategory.TOOL_EXECUTION
            ),
        ))

    if case.max_backend_tool_errors is not None:
        ok = run.backend_tool_error_count <= case.max_backend_tool_errors
        grades.append(GradeResult(
            name="backend_tool_error_budget",
            dimension=EvalDimension.RELIABILITY,
            passed=ok,
            score=1.0 if ok else 0.0,
            reason=(
                f"backend_tool_errors={run.backend_tool_error_count} <= "
                f"{case.max_backend_tool_errors}"
                if ok
                else (
                    f"backend_tool_errors={run.backend_tool_error_count} > "
                    f"{case.max_backend_tool_errors}"
                )
            ),
            failure_category=(
                FailureCategory.NONE if ok else FailureCategory.TOOL_EXECUTION
            ),
        ))

    if case.max_guard_blocks is not None:
        ok = run.guard_block_count <= case.max_guard_blocks
        grades.append(GradeResult(
            name="guard_block_budget",
            dimension=EvalDimension.EFFICIENCY,
            passed=ok,
            score=1.0 if ok else 0.0,
            reason=(
                f"guard_blocks={run.guard_block_count} <= {case.max_guard_blocks}"
                if ok
                else (
                    f"guard_blocks={run.guard_block_count} > "
                    f"{case.max_guard_blocks}"
                )
            ),
            failure_category=(
                FailureCategory.NONE
                if ok
                else FailureCategory.INEFFICIENT_TOOL_USE
            ),
        ))

    if case.max_tool_calls is not None:
        ok = run.tool_calls <= case.max_tool_calls
        grades.append(GradeResult(
            name="tool_call_budget",
            dimension=EvalDimension.EFFICIENCY,
            passed=ok,
            score=1.0 if ok else 0.0,
            reason=(
                f"tool_calls={run.tool_calls} <= {case.max_tool_calls}"
                if ok
                else f"tool_calls={run.tool_calls} > {case.max_tool_calls}"
            ),
            failure_category=(
                FailureCategory.NONE
                if ok
                else FailureCategory.INEFFICIENT_TOOL_USE
            ),
        ))

    if (
        case.max_planner_retries is not None
        and run.mode == ExecutionMode.ORCHESTRATED
    ):
        ok = run.planner_retries <= case.max_planner_retries
        grades.append(GradeResult(
            name="planner_retry_budget",
            dimension=EvalDimension.EFFICIENCY,
            passed=ok,
            score=1.0 if ok else 0.0,
            reason=(
                f"planner_retries={run.planner_retries} <= "
                f"{case.max_planner_retries}"
                if ok
                else (
                    f"planner_retries={run.planner_retries} > "
                    f"{case.max_planner_retries}"
                )
            ),
            failure_category=(
                FailureCategory.NONE if ok else FailureCategory.PERFORMANCE
            ),
        ))

    if case.max_total_tokens is not None:
        if run.total_tokens is None:
            ok = False
            reason = "total_tokens unavailable; cannot verify token budget"
        else:
            ok = run.total_tokens <= case.max_total_tokens
            reason = (
                f"total_tokens={run.total_tokens} <= {case.max_total_tokens}"
                if ok
                else f"total_tokens={run.total_tokens} > {case.max_total_tokens}"
            )
        grades.append(GradeResult(
            name="token_budget",
            dimension=EvalDimension.EFFICIENCY,
            passed=ok,
            score=1.0 if ok else 0.0,
            reason=reason,
            failure_category=(
                FailureCategory.NONE if ok else FailureCategory.PERFORMANCE
            ),
        ))

    if case.max_wall_latency_ms is not None:
        ok = run.wall_latency_ms <= case.max_wall_latency_ms
        grades.append(GradeResult(
            name="latency_slo",
            dimension=EvalDimension.EFFICIENCY,
            passed=ok,
            score=1.0 if ok else 0.0,
            reason=(
                f"{run.wall_latency_ms:.1f}ms <= {case.max_wall_latency_ms:.1f}ms"
                if ok
                else f"{run.wall_latency_ms:.1f}ms > {case.max_wall_latency_ms:.1f}ms"
            ),
            failure_category=(
                FailureCategory.NONE if ok else FailureCategory.PERFORMANCE
            ),
        ))

    return tuple(grades)
