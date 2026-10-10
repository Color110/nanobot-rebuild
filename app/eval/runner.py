from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from time import perf_counter
from uuid import uuid4

from app.agent_loop import AgentLoop
from app.execution_mode import ExecutionMode
from app.orchestration.models import TaskStatus, WorkflowStatus

from .failure import classify_exception, classify_orchestration_result
from .graders import grade_run
from .metrics import ModelPricing, summarize_mode
from .models import (
    EvalCase,
    EvalDimension,
    EvalRunResult,
    EvalSuiteResult,
    FailureCategory,
    GradeResult,
    TokenSource,
)
from .trace_reader import JsonlTraceReader


def _dimension_pass(
    grades: tuple[GradeResult, ...],
    dimension: EvalDimension,
) -> bool | None:
    scoped = [grade for grade in grades if grade.dimension == dimension]
    if not scoped:
        return None
    return all(grade.passed for grade in scoped)


def _planner_diagnostics_from_exception(exc: Exception):
    return getattr(exc, "diagnostics", None)


class EvalRunner:
    def __init__(
        self,
        *,
        agent_loop: AgentLoop,
        trace_reader: JsonlTraceReader | None = None,
        pricing: ModelPricing | None = None,
        cleanup_sessions: bool = True,
    ) -> None:
        self._agent_loop = agent_loop
        self._trace_reader = trace_reader
        self._pricing = pricing
        self._cleanup_sessions = cleanup_sessions

    async def run_suite(
        self,
        cases: tuple[EvalCase, ...] | list[EvalCase],
    ) -> EvalSuiteResult:
        suite_id = f"eval_{uuid4().hex}"
        results: list[EvalRunResult] = []
        for case in cases:
            for mode in case.modes:
                for repeat_index in range(1, case.repeats + 1):
                    results.append(
                        await self.run_case(
                            case,
                            mode=mode,
                            repeat_index=repeat_index,
                        )
                    )

        summaries = tuple(
            summarize_mode(mode, results)
            for mode in ExecutionMode
            if any(r.mode == mode for r in results)
        )
        failure_counts = Counter(
            r.failure_category.value
            for r in results
            if r.failure_category != FailureCategory.NONE
        )
        return EvalSuiteResult(
            suite_id=suite_id,
            created_at=datetime.now(timezone.utc).isoformat(),
            results=tuple(results),
            by_mode=summaries,
            failure_counts=dict(failure_counts),
        )

    async def run_case(
        self,
        case: EvalCase,
        *,
        mode: ExecutionMode,
        repeat_index: int = 1,
    ) -> EvalRunResult:
        run_id = f"run_{uuid4().hex}"
        session_id = (
            f"eval_{case.case_id[:28]}_"
            f"{mode.value[:4]}_{uuid4().hex[:8]}"
        )
        started = perf_counter()

        try:
            turn = await self._agent_loop.process_user_message(
                session_id=session_id,
                content=case.prompt,
                mode=mode,
            )
            wall_ms = (perf_counter() - started) * 1000
            run = self._from_turn(
                case,
                turn,
                run_id,
                repeat_index,
                wall_ms,
            )
        except Exception as exc:
            wall_ms = (perf_counter() - started) * 1000
            category = classify_exception(exc)
            diagnostics = _planner_diagnostics_from_exception(exc)

            planner_attempts = getattr(diagnostics, "attempts", 0)
            planner_retries = getattr(diagnostics, "retries", 0)
            input_tokens = getattr(diagnostics, "input_tokens", 0) or 0
            output_tokens = getattr(diagnostics, "output_tokens", 0) or 0
            usage_complete = bool(
                getattr(diagnostics, "provider_usage_complete", False)
            )
            total_tokens = (
                input_tokens + output_tokens
                if usage_complete
                else None
            )
            cost = (
                self._pricing.estimate(input_tokens, output_tokens)
                if self._pricing and usage_complete
                else None
            )

            run = EvalRunResult(
                run_id=run_id,
                case_id=case.case_id,
                mode=mode,
                repeat_index=repeat_index,
                tags=case.tags,
                passed=False,
                execution_succeeded=False,
                wall_latency_ms=wall_ms,
                planner_attempts=planner_attempts,
                planner_retries=planner_retries,
                input_tokens=(input_tokens if diagnostics is not None else None),
                output_tokens=(output_tokens if diagnostics is not None else None),
                total_tokens=total_tokens,
                token_source=(
                    TokenSource.PROVIDER
                    if usage_complete
                    else TokenSource.UNAVAILABLE
                ),
                estimated_cost=cost,
                cost_currency=(
                    self._pricing.currency
                    if cost is not None and self._pricing
                    else None
                ),
                failure_category=category,
                failure_detail=str(exc),
                error_type=type(exc).__name__,
                error_message=str(exc),
            )

        grades = grade_run(case, run)
        run.grades = grades
        run.correctness_pass = _dimension_pass(
            grades,
            EvalDimension.CORRECTNESS,
        )
        run.reliability_pass = _dimension_pass(
            grades,
            EvalDimension.RELIABILITY,
        )
        run.efficiency_pass = _dimension_pass(
            grades,
            EvalDimension.EFFICIENCY,
        )
        run.passed = bool(grades) and all(g.passed for g in grades)

        if run.failure_category == FailureCategory.NONE:
            failed_grade = next((g for g in grades if not g.passed), None)
            if failed_grade is not None:
                run.failure_category = failed_grade.failure_category
                run.failure_detail = failed_grade.reason

        if self._cleanup_sessions:
            try:
                self._agent_loop.session_manager.get_session_path(
                    session_id
                ).unlink(missing_ok=True)
            except Exception:
                pass
        return run

    def _from_turn(
        self,
        case,
        turn,
        run_id,
        repeat_index,
        wall_ms,
    ) -> EvalRunResult:
        if turn.mode == ExecutionMode.SINGLE:
            result = turn.run_result
            assert result is not None
            tools = tuple(record.name for record in result.tools_used)
            successful_tools = tuple(
                record.name
                for record in result.tools_used
                if not record.is_error
            )
            tool_errors = sum(
                1 for record in result.tools_used if record.is_error
            )
            guard_blocks = sum(
                1
                for record in result.tools_used
                if record.is_error
                and record.error_type == "WEB_FETCH_REPEAT_BLOCKED"
            )
            backend_tool_errors = tool_errors - guard_blocks
            if result.usage.provider_usage_complete:
                input_tokens = result.usage.input_tokens
                output_tokens = result.usage.output_tokens
                total_tokens = result.usage.total_tokens
                source = TokenSource.PROVIDER
            else:
                input_tokens = result.context_stats.estimated_input_tokens
                output_tokens = None
                total_tokens = None
                source = TokenSource.PARTIAL

            cost = (
                self._pricing.estimate(input_tokens, output_tokens)
                if self._pricing
                else None
            )
            return EvalRunResult(
                run_id=run_id,
                case_id=case.case_id,
                mode=turn.mode,
                repeat_index=repeat_index,
                tags=case.tags,
                execution_succeeded=True,
                final_content=result.final_content,
                wall_latency_ms=wall_ms,
                llm_calls=result.usage.llm_calls,
                tool_calls=len(result.tools_used),
                tool_names=tools,
                successful_tool_calls=len(successful_tools),
                successful_tool_names=successful_tools,
                tool_error_count=tool_errors,
                backend_tool_error_count=backend_tool_errors,
                guard_block_count=guard_blocks,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=total_tokens,
                token_source=source,
                estimated_cost=cost,
                cost_currency=(
                    self._pricing.currency
                    if cost is not None and self._pricing
                    else None
                ),
                failure_category=FailureCategory.NONE,
            )

        result = turn.orchestration_result
        assert result is not None
        trace = (
            self._trace_reader.read(result.trace_id)
            if self._trace_reader
            else None
        )
        task_results = list(result.task_results.values())
        success_count = sum(
            1 for r in task_results if r.status == TaskStatus.SUCCEEDED
        )
        fail_count = sum(
            1
            for r in task_results
            if r.status
            in {
                TaskStatus.FAILED,
                TaskStatus.TIMED_OUT,
                TaskStatus.CANCELLED,
            }
        )
        skipped_count = sum(
            1 for r in task_results if r.status == TaskStatus.SKIPPED
        )
        task_count = len(task_results)
        task_success_rate = (
            success_count / task_count if task_count else None
        )
        planner_data_present = isinstance(
            result.data.get("planner"),
            dict,
        )
        planner_usage_complete = (
            result.metrics.planner_provider_usage_complete
            if planner_data_present
            else True
        )
        end_to_end_usage_complete = (
            result.metrics.provider_usage_complete
            and planner_usage_complete
        )
        end_to_end_input_tokens = (
            result.metrics.input_tokens
            + result.metrics.planner_input_tokens
        )
        end_to_end_output_tokens = (
            result.metrics.output_tokens
            + result.metrics.planner_output_tokens
        )
        total_tokens = (
            end_to_end_input_tokens + end_to_end_output_tokens
            if end_to_end_usage_complete
            else None
        )
        cost = (
            self._pricing.estimate(
                end_to_end_input_tokens,
                end_to_end_output_tokens,
            )
            if self._pricing and end_to_end_usage_complete
            else None
        )
        planner_data = result.data.get("planner", {})
        planner_attempts = int(planner_data.get("attempts", 0) or 0)
        planner_retries = int(planner_data.get("retries", 0) or 0)

        category, detail = classify_orchestration_result(result)
        if (
            result.status == WorkflowStatus.SUCCEEDED
            and category == FailureCategory.NONE
        ):
            execution_succeeded = True
        else:
            execution_succeeded = result.status in {
                WorkflowStatus.SUCCEEDED,
                WorkflowStatus.PARTIAL_SUCCESS,
            }

        return EvalRunResult(
            run_id=run_id,
            case_id=case.case_id,
            mode=turn.mode,
            repeat_index=repeat_index,
            tags=case.tags,
            execution_succeeded=execution_succeeded,
            final_content=result.summary,
            workflow_id=result.workflow_id,
            trace_id=result.trace_id,
            workflow_status=result.status,
            wall_latency_ms=wall_ms,
            llm_calls=(
                result.metrics.llm_calls
                + result.metrics.planner_llm_calls
            ),
            tool_calls=result.metrics.tool_calls,
            tool_names=trace.tool_names if trace else (),
            successful_tool_calls=(
                trace.successful_tool_calls if trace else 0
            ),
            successful_tool_names=(
                trace.successful_tool_names if trace else ()
            ),
            tool_error_count=trace.tool_error_count if trace else 0,
            backend_tool_error_count=(
                trace.backend_tool_error_count if trace else 0
            ),
            guard_block_count=trace.guard_block_count if trace else 0,
            planner_attempts=planner_attempts,
            planner_retries=planner_retries,
            input_tokens=end_to_end_input_tokens,
            output_tokens=end_to_end_output_tokens,
            total_tokens=total_tokens,
            token_source=(
                TokenSource.PROVIDER
                if end_to_end_usage_complete
                else TokenSource.PARTIAL
            ),
            estimated_cost=cost,
            cost_currency=(
                self._pricing.currency
                if cost is not None and self._pricing
                else None
            ),
            task_count=task_count,
            task_success_count=success_count,
            task_failure_count=fail_count,
            task_skipped_count=skipped_count,
            task_success_rate=task_success_rate,
            failure_category=category,
            failure_detail=detail,
        )
