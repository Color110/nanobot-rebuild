from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.orchestration.models import (
    EvidenceRef,
    TaskError,
    TaskMetrics,
    TaskResult,
    TaskStatus,
    WorkflowStatus,
)
from app.orchestration.scheduler import WorkflowRunResult


class OrchestrationMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    llm_calls: int = Field(default=0, ge=0)
    tool_calls: int = Field(default=0, ge=0)
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    provider_usage_complete: bool = False

    # Planner is measured separately so existing task/subagent metrics keep
    # their original semantics. End-to-end Eval may sum both layers.
    planner_llm_calls: int = Field(default=0, ge=0)
    planner_input_tokens: int = Field(default=0, ge=0)
    planner_output_tokens: int = Field(default=0, ge=0)
    planner_provider_usage_complete: bool = False

    # Sum of task latency is useful for cost/effort analysis, but because
    # parallel tasks overlap it must not be presented as workflow wall time.
    task_latency_ms_sum: float = Field(default=0.0, ge=0)


class OrchestrationTaskError(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    task_id: str
    status: TaskStatus
    error: TaskError


class OrchestrationResult(BaseModel):
    """Stable, caller-facing result for one completed orchestration attempt."""

    model_config = ConfigDict(extra="forbid")

    workflow_id: str
    trace_id: str
    status: WorkflowStatus

    summary: str = ""
    data: dict[str, Any] = Field(default_factory=dict)

    output_task_ids: tuple[str, ...] = ()
    task_results: dict[str, TaskResult] = Field(default_factory=dict)
    evidence: tuple[EvidenceRef, ...] = ()
    errors: tuple[OrchestrationTaskError, ...] = ()
    metrics: OrchestrationMetrics = Field(default_factory=OrchestrationMetrics)


class DeterministicResultReducer:
    """
    Deterministically reduce WorkflowRunResult into OrchestrationResult.

    This layer does not ask an LLM whether the workflow succeeded and does not
    hide failed/skipped tasks. A semantic/LLM synthesizer can be added later on
    top of this structured result.
    """

    def reduce(
        self,
        run_result: WorkflowRunResult,
        *,
        trace_id: str,
    ) -> OrchestrationResult:
        task_results = dict(run_result.task_results)
        task_states = dict(run_result.task_states)

        output_task_ids = self._resolve_output_tasks(
            task_states=task_states,
            task_results=task_results,
        )

        summary = self._build_summary(
            status=run_result.status,
            output_task_ids=output_task_ids,
            task_results=task_results,
        )

        evidence = self._dedupe_evidence(task_results)
        errors = self._collect_errors(task_results)
        metrics = self._aggregate_metrics(task_results)

        successful = [
            task_id
            for task_id, result in task_results.items()
            if result.status == TaskStatus.SUCCEEDED
        ]
        failed = [
            task_id
            for task_id, result in task_results.items()
            if result.status in {
                TaskStatus.FAILED,
                TaskStatus.TIMED_OUT,
                TaskStatus.CANCELLED,
            }
        ]
        skipped = [
            task_id
            for task_id, result in task_results.items()
            if result.status == TaskStatus.SKIPPED
        ]

        outputs = {
            task_id: task_results[task_id].data
            for task_id in output_task_ids
            if task_id in task_results
        }

        return OrchestrationResult(
            workflow_id=run_result.workflow_id,
            trace_id=trace_id,
            status=run_result.status,
            summary=summary,
            data={
                "outputs": outputs,
                "successful_tasks": successful,
                "failed_tasks": failed,
                "skipped_tasks": skipped,
            },
            output_task_ids=output_task_ids,
            task_results=task_results,
            evidence=evidence,
            errors=errors,
            metrics=metrics,
        )

    @staticmethod
    def _resolve_output_tasks(
        *,
        task_states,
        task_results: dict[str, TaskResult],
    ) -> tuple[str, ...]:
        depended_on = {
            dependency_id
            for task in task_states.values()
            for dependency_id in task.dependencies
        }

        leaf_ids = tuple(
            task_id
            for task_id in task_states
            if task_id not in depended_on
        )

        successful_leaves = tuple(
            task_id
            for task_id in leaf_ids
            if (
                task_id in task_results
                and task_results[task_id].status == TaskStatus.SUCCEEDED
            )
        )
        if successful_leaves:
            return successful_leaves

        # A failed workflow may have no successful leaf. Preserve useful
        # successful partial results instead of pretending there is an output.
        return tuple(
            task_id
            for task_id, result in task_results.items()
            if result.status == TaskStatus.SUCCEEDED
        )

    @staticmethod
    def _build_summary(
        *,
        status: WorkflowStatus,
        output_task_ids: tuple[str, ...],
        task_results: dict[str, TaskResult],
    ) -> str:
        summaries = [
            task_results[task_id].summary.strip()
            for task_id in output_task_ids
            if (
                task_id in task_results
                and task_results[task_id].summary.strip()
            )
        ]

        if len(summaries) == 1:
            return summaries[0]

        if summaries:
            return "\n\n".join(summaries)

        return f"Workflow completed with status={status.value}"

    @staticmethod
    def _dedupe_evidence(
        task_results: dict[str, TaskResult],
    ) -> tuple[EvidenceRef, ...]:
        seen: set[tuple[str, str | None, str | None]] = set()
        output: list[EvidenceRef] = []

        for result in task_results.values():
            for evidence in result.evidence:
                key = (
                    evidence.source,
                    evidence.ref,
                    evidence.snippet,
                )
                if key in seen:
                    continue
                seen.add(key)
                output.append(evidence)

        return tuple(output)

    @staticmethod
    def _collect_errors(
        task_results: dict[str, TaskResult],
    ) -> tuple[OrchestrationTaskError, ...]:
        errors: list[OrchestrationTaskError] = []

        for task_id, result in task_results.items():
            if result.error is None:
                continue
            errors.append(
                OrchestrationTaskError(
                    task_id=task_id,
                    status=result.status,
                    error=result.error,
                )
            )

        return tuple(errors)

    @staticmethod
    def _aggregate_metrics(
        task_results: dict[str, TaskResult],
    ) -> OrchestrationMetrics:
        llm_calls = 0
        tool_calls = 0
        input_tokens = 0
        output_tokens = 0
        latency_sum = 0.0
        usage_flags: list[bool] = []

        for result in task_results.values():
            metrics: TaskMetrics = result.metrics
            llm_calls += metrics.llm_calls
            tool_calls += metrics.tool_calls
            input_tokens += metrics.input_tokens or 0
            output_tokens += metrics.output_tokens or 0
            latency_sum += metrics.latency_ms or 0.0
            if metrics.llm_calls > 0:
                usage_flags.append(metrics.provider_usage_complete)

        return OrchestrationMetrics(
            llm_calls=llm_calls,
            tool_calls=tool_calls,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            provider_usage_complete=(bool(usage_flags) and all(usage_flags)),
            task_latency_ms_sum=latency_sum,
        )
