from __future__ import annotations

from dataclasses import dataclass
from statistics import mean

from app.execution_mode import ExecutionMode
from app.orchestration.models import WorkflowStatus

from .models import EvalRunResult, ModeSummary


@dataclass(frozen=True)
class ModelPricing:
    input_per_million: float
    output_per_million: float
    currency: str = "USD"

    def estimate(
        self,
        input_tokens: int | None,
        output_tokens: int | None,
    ) -> float | None:
        if input_tokens is None or output_tokens is None:
            return None
        return (
            input_tokens / 1_000_000 * self.input_per_million
            + output_tokens / 1_000_000 * self.output_per_million
        )


def _percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    xs = sorted(values)
    pos = (len(xs) - 1) * q
    lo = int(pos)
    hi = min(lo + 1, len(xs) - 1)
    frac = pos - lo
    return xs[lo] * (1 - frac) + xs[hi] * frac


def _optional_pass_rate(values: list[bool | None]) -> float | None:
    measured = [value for value in values if value is not None]
    if not measured:
        return None
    return sum(1 for value in measured if value) / len(measured)


def summarize_mode(
    mode: ExecutionMode,
    results: list[EvalRunResult],
) -> ModeSummary:
    subset = [r for r in results if r.mode == mode]
    if not subset:
        return ModeSummary(
            mode=mode,
            runs=0,
            passed=0,
            pass_rate=0.0,
            execution_success_rate=0.0,
        )

    passed = sum(1 for r in subset if r.passed)
    exec_ok = sum(1 for r in subset if r.execution_succeeded)
    latencies = [r.wall_latency_ms for r in subset]
    tokens = [r.total_tokens for r in subset if r.total_tokens is not None]
    costs = [r.estimated_cost for r in subset if r.estimated_cost is not None]

    workflow_success_rate = None
    task_success_rate = None
    if mode == ExecutionMode.ORCHESTRATED:
        workflow_success_rate = (
            sum(
                1
                for r in subset
                if r.workflow_status == WorkflowStatus.SUCCEEDED
            )
            / len(subset)
        )
        total_tasks = sum(r.task_count for r in subset)
        task_success_rate = (
            sum(r.task_success_count for r in subset) / total_tasks
            if total_tasks
            else None
        )

    return ModeSummary(
        mode=mode,
        runs=len(subset),
        passed=passed,
        pass_rate=passed / len(subset),
        correctness_pass_rate=_optional_pass_rate(
            [r.correctness_pass for r in subset]
        ),
        reliability_pass_rate=_optional_pass_rate(
            [r.reliability_pass for r in subset]
        ),
        efficiency_pass_rate=_optional_pass_rate(
            [r.efficiency_pass for r in subset]
        ),
        execution_success_rate=exec_ok / len(subset),
        workflow_success_rate=workflow_success_rate,
        task_success_rate=task_success_rate,
        avg_wall_latency_ms=mean(latencies),
        p50_wall_latency_ms=_percentile(latencies, 0.50),
        p95_wall_latency_ms=_percentile(latencies, 0.95),
        avg_tool_calls=mean(r.tool_calls for r in subset),
        avg_tool_errors=mean(r.tool_error_count for r in subset),
        avg_backend_tool_errors=mean(
            r.backend_tool_error_count for r in subset
        ),
        avg_guard_blocks=mean(r.guard_block_count for r in subset),
        avg_planner_attempts=(
            mean(r.planner_attempts for r in subset)
            if mode == ExecutionMode.ORCHESTRATED
            else None
        ),
        avg_planner_retries=(
            mean(r.planner_retries for r in subset)
            if mode == ExecutionMode.ORCHESTRATED
            else None
        ),
        planner_retry_rate=(
            sum(1 for r in subset if r.planner_retries > 0) / len(subset)
            if mode == ExecutionMode.ORCHESTRATED
            else None
        ),
        avg_total_tokens=mean(tokens) if tokens else None,
        avg_estimated_cost=mean(costs) if costs else None,
    )
