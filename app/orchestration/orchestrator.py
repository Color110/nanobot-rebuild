from __future__ import annotations

from typing import Any
from uuid import uuid4

from app.orchestration.graph import TaskPlanValidator
from app.orchestration.planner import LLMPlanner, PlannerDiagnostics
from app.orchestration.reducer import (
    DeterministicResultReducer,
    OrchestrationMetrics,
    OrchestrationResult,
)
from app.orchestration.scheduler import TaskScheduler
from app.orchestration.tracing import (
    NullTraceSink,
    TraceEventType,
    TraceSink,
    emit_trace,
    new_trace_id,
)


class WorkflowOrchestrator:
    """
    Top-level lifecycle coordinator for Multi-Agent workflows.

    It coordinates components; it does not replace them:
    Planner -> Validator -> Scheduler -> Reducer.
    """

    def __init__(
        self,
        *,
        planner: LLMPlanner,
        validator: TaskPlanValidator,
        scheduler: TaskScheduler,
        reducer: DeterministicResultReducer | None = None,
        trace_sink: TraceSink | None = None,
    ) -> None:
        self._planner = planner
        self._validator = validator
        self._scheduler = scheduler
        self._reducer = reducer or DeterministicResultReducer()
        self._trace_sink = trace_sink or NullTraceSink()

    @staticmethod
    def _planner_failure_attributes(exc: Exception) -> dict[str, Any]:
        diagnostics = getattr(exc, "diagnostics", None)
        if not isinstance(diagnostics, PlannerDiagnostics):
            return {}
        return {
            "planner_attempts": diagnostics.attempts,
            "planner_retries": diagnostics.retries,
            "planner_failure_reasons": list(diagnostics.failure_reasons),
            "planner_input_tokens": diagnostics.input_tokens,
            "planner_output_tokens": diagnostics.output_tokens,
            "planner_provider_usage_complete": (
                diagnostics.provider_usage_complete
            ),
        }

    @staticmethod
    def _attach_planner_diagnostics(
        result: OrchestrationResult,
        diagnostics: PlannerDiagnostics,
    ) -> OrchestrationResult:
        # Keep existing SubAgent metric semantics stable and attach Planner
        # usage in dedicated fields. Eval can aggregate both for end-to-end
        # cost/latency analysis without breaking M6 regression expectations.
        metrics = result.metrics
        combined_metrics = OrchestrationMetrics(
            llm_calls=metrics.llm_calls,
            tool_calls=metrics.tool_calls,
            input_tokens=metrics.input_tokens,
            output_tokens=metrics.output_tokens,
            provider_usage_complete=metrics.provider_usage_complete,
            planner_llm_calls=diagnostics.attempts,
            planner_input_tokens=diagnostics.input_tokens,
            planner_output_tokens=diagnostics.output_tokens,
            planner_provider_usage_complete=(
                diagnostics.provider_usage_complete
            ),
            task_latency_ms_sum=metrics.task_latency_ms_sum,
        )

        data = dict(result.data)
        data["planner"] = {
            "attempts": diagnostics.attempts,
            "retries": diagnostics.retries,
            "failure_reasons": list(diagnostics.failure_reasons),
            "input_tokens": diagnostics.input_tokens,
            "output_tokens": diagnostics.output_tokens,
            "provider_usage_complete": diagnostics.provider_usage_complete,
        }

        return result.model_copy(
            update={
                "data": data,
                "metrics": combined_metrics,
            }
        )

    async def run(
        self,
        *,
        user_goal: str,
        context: dict[str, Any] | None = None,
        workflow_id: str | None = None,
        trace_id: str | None = None,
    ) -> OrchestrationResult:
        resolved_workflow_id = workflow_id or f"wf_{uuid4().hex}"
        resolved_trace_id = trace_id or new_trace_id()

        await emit_trace(
            self._trace_sink,
            trace_id=resolved_trace_id,
            event_type=TraceEventType.WORKFLOW_STARTED,
            workflow_id=resolved_workflow_id,
            status="RUNNING",
            attributes={"user_goal": user_goal},
        )

        try:
            await emit_trace(
                self._trace_sink,
                trace_id=resolved_trace_id,
                event_type=TraceEventType.PLANNER_STARTED,
                workflow_id=resolved_workflow_id,
            )

            planner_result = await self._planner.plan_with_diagnostics(
                user_goal=user_goal,
                context=context,
                trace_sink=self._trace_sink,
                trace_id=resolved_trace_id,
                workflow_id=resolved_workflow_id,
            )
            plan = planner_result.plan
            planner_diagnostics = planner_result.diagnostics

            await emit_trace(
                self._trace_sink,
                trace_id=resolved_trace_id,
                event_type=TraceEventType.PLANNER_COMPLETED,
                workflow_id=resolved_workflow_id,
                attributes={
                    "task_count": len(plan.tasks),
                    "planner_attempts": planner_diagnostics.attempts,
                    "planner_retries": planner_diagnostics.retries,
                    "planner_input_tokens": planner_diagnostics.input_tokens,
                    "planner_output_tokens": planner_diagnostics.output_tokens,
                    "planner_provider_usage_complete": (
                        planner_diagnostics.provider_usage_complete
                    ),
                },
            )

            graph = self._validator.validate_and_resolve(
                plan,
                workflow_id=resolved_workflow_id,
            )

            await emit_trace(
                self._trace_sink,
                trace_id=resolved_trace_id,
                event_type=TraceEventType.VALIDATION_COMPLETED,
                workflow_id=resolved_workflow_id,
                attributes={
                    "topological_order": list(graph.topological_order),
                    "depth_by_task": graph.depth_by_task,
                },
            )

            run_result = await self._scheduler.run(
                graph,
                trace_id=resolved_trace_id,
            )

            result = self._reducer.reduce(
                run_result,
                trace_id=resolved_trace_id,
            )
            result = self._attach_planner_diagnostics(
                result,
                planner_diagnostics,
            )

            await emit_trace(
                self._trace_sink,
                trace_id=resolved_trace_id,
                event_type=TraceEventType.REDUCTION_COMPLETED,
                workflow_id=resolved_workflow_id,
                status=result.status.value,
                attributes={
                    "output_task_ids": list(result.output_task_ids),
                    "error_count": len(result.errors),
                },
            )

            await emit_trace(
                self._trace_sink,
                trace_id=resolved_trace_id,
                event_type=TraceEventType.WORKFLOW_FINISHED,
                workflow_id=resolved_workflow_id,
                status=result.status.value,
            )

            return result

        except Exception as exc:
            attributes = {
                "error_type": type(exc).__name__,
                "error": str(exc),
            }
            attributes.update(self._planner_failure_attributes(exc))
            await emit_trace(
                self._trace_sink,
                trace_id=resolved_trace_id,
                event_type=TraceEventType.WORKFLOW_FAILED,
                workflow_id=resolved_workflow_id,
                status="FAILED",
                attributes=attributes,
            )
            raise

    async def resume(
        self,
        *,
        workflow_id: str,
        trace_id: str | None = None,
    ) -> OrchestrationResult:
        """
        Resume an already-persisted workflow.

        Planner and Validator are intentionally not called again. A resume is a
        new observability attempt, so by default it gets a fresh trace_id while
        preserving the same durable workflow_id.
        """

        resolved_trace_id = trace_id or new_trace_id()

        await emit_trace(
            self._trace_sink,
            trace_id=resolved_trace_id,
            event_type=TraceEventType.WORKFLOW_RESUMED,
            workflow_id=workflow_id,
            status="RUNNING",
        )

        try:
            run_result = await self._scheduler.resume(
                workflow_id,
                trace_id=resolved_trace_id,
            )

            result = self._reducer.reduce(
                run_result,
                trace_id=resolved_trace_id,
            )

            await emit_trace(
                self._trace_sink,
                trace_id=resolved_trace_id,
                event_type=TraceEventType.REDUCTION_COMPLETED,
                workflow_id=workflow_id,
                status=result.status.value,
                attributes={
                    "output_task_ids": list(result.output_task_ids),
                    "error_count": len(result.errors),
                },
            )

            await emit_trace(
                self._trace_sink,
                trace_id=resolved_trace_id,
                event_type=TraceEventType.WORKFLOW_FINISHED,
                workflow_id=workflow_id,
                status=result.status.value,
            )

            return result

        except Exception as exc:
            await emit_trace(
                self._trace_sink,
                trace_id=resolved_trace_id,
                event_type=TraceEventType.WORKFLOW_FAILED,
                workflow_id=workflow_id,
                status="FAILED",
                attributes={
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                },
            )
            raise
