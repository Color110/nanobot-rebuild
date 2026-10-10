from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

from app.orchestration import (
    AgentSpec,
    DeterministicResultReducer,
    InMemoryTraceSink,
    LLMPlanner,
    OrchestrationPolicy,
    SQLiteTaskStore,
    TaskMetrics,
    TaskPlanValidator,
    TaskResult,
    TaskScheduler,
    TaskStatus,
    WorkflowOrchestrator,
    WorkflowStatus,
)
from app.orchestration.models import RuntimeTask
from app.providers import FakeProvider, ProviderResponse, ToolCallRequest


class FakeTaskExecutor:
    async def execute(
        self,
        task: RuntimeTask,
        *,
        dependency_results: dict[str, TaskResult] | None = None,
        trace_id: str | None = None,
    ) -> TaskResult:
        dependency_results = dependency_results or {}
        await asyncio.sleep(0.03)

        if task.task_id == "write_report":
            text = "最终报告：产品与融资调研均已完成。"
        else:
            text = f"{task.task_id} result"

        return TaskResult(
            workflow_id=task.workflow_id,
            task_id=task.task_id,
            status=TaskStatus.SUCCEEDED,
            summary=text,
            data={
                "final_content": text,
                "dependency_ids": list(dependency_results),
            },
            metrics=TaskMetrics(
                latency_ms=30.0,
                llm_calls=1,
                tool_calls=1 if task.agent_type == "researcher" else 0,
                input_tokens=100,
                output_tokens=40,
            ),
            trace_id=trace_id,
        )


async def main() -> None:
    agent_specs = {
        "researcher": AgentSpec(
            agent_type="researcher",
            system_prompt="负责研究。",
            allowed_tools=frozenset({"search_web"}),
        ),
        "writer": AgentSpec(
            agent_type="writer",
            system_prompt="负责写报告。",
            allowed_tools=frozenset(),
        ),
    }

    policy = OrchestrationPolicy(
        max_tasks=8,
        max_depth=4,
        max_concurrency=2,
        workflow_timeout_seconds=10.0,
    )

    provider = FakeProvider(
        responses=[
            ProviderResponse(
                content="",
                tool_calls=[
                    ToolCallRequest(
                        id="plan_call_1",
                        name="submit_task_plan",
                        arguments={
                            "tasks": [
                                {
                                    "task_id": "research_product",
                                    "objective": "研究产品",
                                    "agent_type": "researcher",
                                    "dependencies": [],
                                    "requested_tools": ["search_web"],
                                },
                                {
                                    "task_id": "research_funding",
                                    "objective": "研究融资",
                                    "agent_type": "researcher",
                                    "dependencies": [],
                                    "requested_tools": ["search_web"],
                                },
                                {
                                    "task_id": "write_report",
                                    "objective": "写最终报告",
                                    "agent_type": "writer",
                                    "dependencies": [
                                        "research_product",
                                        "research_funding",
                                    ],
                                    "requested_tools": [],
                                },
                            ]
                        },
                    )
                ],
            )
        ]
    )

    planner = LLMPlanner(
        provider=provider,
        agent_specs=agent_specs,
        policy=policy,
    )
    validator = TaskPlanValidator(
        agent_specs=agent_specs,
        policy=policy,
    )

    trace_sink = InMemoryTraceSink()

    with tempfile.TemporaryDirectory() as tmp:
        store = SQLiteTaskStore(Path(tmp) / "m6.sqlite3")
        scheduler = TaskScheduler(
            executor=FakeTaskExecutor(),
            policy=policy,
            store=store,
            worker_id="worker_m6_smoke",
            lease_seconds=2.0,
            heartbeat_interval_seconds=0.5,
            poll_interval_seconds=0.01,
            trace_sink=trace_sink,
        )

        orchestrator = WorkflowOrchestrator(
            planner=planner,
            validator=validator,
            scheduler=scheduler,
            reducer=DeterministicResultReducer(),
            trace_sink=trace_sink,
        )

        result = await orchestrator.run(
            user_goal="研究产品和融资并写报告",
            workflow_id="wf_m6_smoke",
            trace_id="trace_m6_smoke",
        )

    assert result.status == WorkflowStatus.SUCCEEDED
    assert result.output_task_ids == ("write_report",)
    assert result.summary == "最终报告：产品与融资调研均已完成。"
    assert result.metrics.llm_calls == 3
    assert result.metrics.tool_calls == 2
    assert result.data["failed_tasks"] == []

    event_types = [event.event_type.value for event in trace_sink.events]
    assert event_types[0] == "WORKFLOW_STARTED"
    assert "PLANNER_STARTED" in event_types
    assert "PLANNER_COMPLETED" in event_types
    assert "VALIDATION_COMPLETED" in event_types
    assert event_types.count("TASK_CLAIMED") == 3
    assert event_types.count("TASK_FINISHED") == 3
    assert "REDUCTION_COMPLETED" in event_types
    assert event_types[-1] == "WORKFLOW_FINISHED"

    print("M6 ORCHESTRATOR SMOKE PASSED")
    print("workflow_id:", result.workflow_id)
    print("trace_id:", result.trace_id)
    print("status:", result.status.value)
    print("output_task_ids:", result.output_task_ids)
    print("summary:", result.summary)
    print("metrics:", result.metrics.model_dump())
    print("trace_events:", event_types)


if __name__ == "__main__":
    asyncio.run(main())
