from __future__ import annotations

import asyncio
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from app.agent import AgentRunResult, AgentUsage, ToolExecutionRecord
from app.agent_loop import AgentTurnResult
from app.context import ContextStats
from app.eval import EvalCase, EvalRunner, JsonlTraceReader
from app.execution_mode import ExecutionMode
from app.orchestration.models import (
    TaskMetrics,
    TaskResult,
    TaskStatus,
    WorkflowStatus,
)
from app.orchestration.reducer import OrchestrationMetrics, OrchestrationResult
from app.session import SessionManager


class FakeEvalAgentLoop:
    def __init__(self, sessions: SessionManager, trace_path: Path) -> None:
        self.session_manager = sessions
        self.trace_path = trace_path
        self._counter = 0

    async def process_user_message(
        self,
        session_id: str,
        content: str,
        *,
        mode: ExecutionMode,
    ):
        session = self.session_manager.get_or_create(session_id)
        self.session_manager.save(session)

        if mode == ExecutionMode.SINGLE:
            stats = ContextStats(
                max_input_tokens=6000,
                estimated_input_tokens=100,
                system_tokens=20,
                memory_tokens=0,
                skills_tokens=0,
                history_tokens=80,
                total_session_messages=1,
                selected_session_messages=1,
                dropped_session_messages=0,
                total_memory_records=0,
                selected_memory_records=0,
                active_skills=(),
            )
            run = AgentRunResult(
                final_content="437",
                messages=[],
                iterations=2,
                tools_used=[
                    ToolExecutionRecord(
                        tool_call_id="tc1",
                        name="calculator",
                        arguments={},
                        output="437",
                    )
                ],
                context_stats=stats,
                skill_selection=None,
                usage=AgentUsage(
                    llm_calls=2,
                    input_tokens=120,
                    output_tokens=20,
                    total_tokens=140,
                    provider_usage_complete=True,
                ),
            )
            return AgentTurnResult(
                session_id=session_id,
                mode=mode,
                run_result=run,
            )

        self._counter += 1
        trace_id = f"trace_eval_hardening_{self._counter}"
        self.trace_path.parent.mkdir(parents=True, exist_ok=True)
        with self.trace_path.open("a", encoding="utf-8") as handle:
            for tool_name in ("web_search", "fetch_web_page"):
                handle.write(
                    json.dumps(
                        {
                            "trace_id": trace_id,
                            "event_type": "TOOL_COMPLETED",
                            "tool_name": tool_name,
                            "status": "SUCCEEDED",
                        }
                    )
                    + "\n"
                )

        task = TaskResult(
            workflow_id="wf_eval_hardening",
            task_id="research",
            status=TaskStatus.SUCCEEDED,
            summary="official page summary",
            metrics=TaskMetrics(
                latency_ms=50,
                llm_calls=2,
                tool_calls=2,
                input_tokens=200,
                output_tokens=40,
                provider_usage_complete=True,
            ),
            trace_id=trace_id,
        )
        orchestration = OrchestrationResult(
            workflow_id="wf_eval_hardening",
            trace_id=trace_id,
            status=WorkflowStatus.SUCCEEDED,
            summary="official page summary",
            output_task_ids=("research",),
            task_results={"research": task},
            metrics=OrchestrationMetrics(
                llm_calls=2,
                tool_calls=2,
                input_tokens=200,
                output_tokens=40,
                provider_usage_complete=True,
                task_latency_ms_sum=50,
            ),
        )
        return AgentTurnResult(
            session_id=session_id,
            mode=mode,
            orchestration_result=orchestration,
        )


async def main() -> None:
    with TemporaryDirectory() as td:
        root = Path(td)
        trace_path = root / "trace.jsonl"
        loop = FakeEvalAgentLoop(
            SessionManager(root / "sessions"),
            trace_path,
        )
        runner = EvalRunner(
            agent_loop=loop,  # type: ignore[arg-type]
            trace_reader=JsonlTraceReader(trace_path),
            cleanup_sessions=True,
        )

        cases = (
            EvalCase(
                case_id="calc",
                prompt="19*23",
                modes=(ExecutionMode.SINGLE,),
                expected_tools=("calculator",),
                required_successful_tools=("calculator",),
                required_text=("437",),
                max_tool_calls=1,
                max_tool_errors=0,
                max_total_tokens=500,
                max_wall_latency_ms=5000,
            ),
            EvalCase(
                case_id="web",
                prompt="research",
                modes=(ExecutionMode.ORCHESTRATED,),
                expected_tools=("web_search", "fetch_web_page"),
                required_successful_tools=(
                    "web_search",
                    "fetch_web_page",
                ),
                min_task_success_rate=1.0,
                max_tool_calls=2,
                max_tool_errors=0,
                max_total_tokens=500,
                max_wall_latency_ms=5000,
            ),
            EvalCase(
                case_id="intentional_efficiency_failure",
                prompt="research",
                modes=(ExecutionMode.ORCHESTRATED,),
                max_tool_calls=1,
            ),
        )

        report = await runner.run_suite(cases)
        assert len(report.results) == 3

        calc, web, inefficient = report.results
        assert calc.passed
        assert calc.correctness_pass is True
        assert calc.reliability_pass is True
        assert calc.efficiency_pass is True
        assert calc.successful_tool_names == ("calculator",)

        assert web.passed
        assert web.reliability_pass is True
        assert web.efficiency_pass is True
        assert set(web.successful_tool_names) == {
            "web_search",
            "fetch_web_page",
        }

        assert not inefficient.passed
        assert inefficient.reliability_pass is True
        assert inefficient.efficiency_pass is False
        assert inefficient.failure_category.value == "INEFFICIENT_TOOL_USE"

        print("M7-B.2 EVAL HARDENING SMOKE PASSED")
        for result in report.results:
            print(
                result.case_id,
                {
                    "passed": result.passed,
                    "correctness": result.correctness_pass,
                    "reliability": result.reliability_pass,
                    "efficiency": result.efficiency_pass,
                    "failure": result.failure_category.value,
                },
            )


if __name__ == "__main__":
    asyncio.run(main())
