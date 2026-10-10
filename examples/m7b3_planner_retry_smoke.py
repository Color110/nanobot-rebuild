from __future__ import annotations

import asyncio

from app.orchestration.models import AgentSpec, TaskBudget
from app.orchestration.planner import (
    LLMPlanner,
    PlannerRetryExhaustedError,
)
from app.orchestration.policy import OrchestrationPolicy
from app.orchestration.tracing import InMemoryTraceSink, TraceEventType
from app.providers.base import (
    LLMProvider,
    ProviderError,
    ProviderResponse,
    ProviderUsage,
    StructuredOutputError,
    ToolCallRequest,
)


class RetryThenSuccessProvider(LLMProvider):
    def __init__(self) -> None:
        self.calls = 0

    @property
    def name(self) -> str:
        return "retry-then-success"

    @property
    def model(self) -> str:
        return "fake"

    async def complete(self, messages, tools=None) -> ProviderResponse:
        self.calls += 1
        if self.calls == 1:
            raise StructuredOutputError(
                "malformed tool arguments",
                stage="tool_arguments_json",
                raw_value='{\"tasks\": [}',
                usage=ProviderUsage(
                    input_tokens=100,
                    output_tokens=20,
                    total_tokens=120,
                ),
            )
        return ProviderResponse(
            content="",
            tool_calls=[
                ToolCallRequest(
                    id="tc_2",
                    name="submit_task_plan",
                    arguments={
                        "plan_version": "1",
                        "tasks": [
                            {
                                "task_id": "answer",
                                "objective": "answer the user",
                                "agent_type": "analyst",
                                "dependencies": [],
                                "requested_tools": [],
                                "required": True,
                                "input_data": {},
                            }
                        ],
                    },
                )
            ],
            usage=ProviderUsage(
                input_tokens=120,
                output_tokens=30,
                total_tokens=150,
            ),
        )


class AlwaysMalformedProvider(RetryThenSuccessProvider):
    async def complete(self, messages, tools=None) -> ProviderResponse:
        self.calls += 1
        raise StructuredOutputError(
            "still malformed",
            stage="tool_arguments_json",
            usage=ProviderUsage(
                input_tokens=50,
                output_tokens=10,
                total_tokens=60,
            ),
        )


class GenericProviderFailure(RetryThenSuccessProvider):
    async def complete(self, messages, tools=None) -> ProviderResponse:
        self.calls += 1
        raise ProviderError("network/auth/rate-limit style failure")


def build_planner(provider: LLMProvider) -> LLMPlanner:
    specs = {
        "analyst": AgentSpec(
            agent_type="analyst",
            system_prompt="Analyze the task.",
            allowed_tools=frozenset(),
            budget=TaskBudget(),
        )
    }
    return LLMPlanner(
        provider=provider,
        agent_specs=specs,
        policy=OrchestrationPolicy(
            max_tasks=4,
            max_depth=2,
            max_concurrency=2,
            workflow_timeout_seconds=60.0,
            max_total_llm_calls=16,
            max_total_tokens=50_000,
        ),
        max_structured_retries=1,
    )


async def main() -> None:
    provider = RetryThenSuccessProvider()
    planner = build_planner(provider)
    sink = InMemoryTraceSink()

    result = await planner.plan_with_diagnostics(
        user_goal="compare A and B",
        trace_sink=sink,
        trace_id="trace_retry_smoke",
        workflow_id="wf_retry_smoke",
    )
    assert provider.calls == 2
    assert result.diagnostics.attempts == 2
    assert result.diagnostics.retries == 1
    assert result.diagnostics.input_tokens == 220
    assert result.diagnostics.output_tokens == 50
    assert result.diagnostics.provider_usage_complete is True
    assert result.plan.tasks[0].task_id == "answer"

    events = [event.event_type for event in sink.events]
    assert events == [
        TraceEventType.PLANNER_ATTEMPT_STARTED,
        TraceEventType.PLANNER_ATTEMPT_FAILED,
        TraceEventType.PLANNER_RETRYING,
        TraceEventType.PLANNER_ATTEMPT_STARTED,
    ]

    exhausted_provider = AlwaysMalformedProvider()
    exhausted = build_planner(exhausted_provider)
    try:
        await exhausted.plan(user_goal="x")
        raise AssertionError("expected PlannerRetryExhaustedError")
    except PlannerRetryExhaustedError as exc:
        assert exc.diagnostics.attempts == 2
        assert exc.diagnostics.retries == 1
        assert exc.diagnostics.input_tokens == 100
        assert exc.diagnostics.output_tokens == 20
        assert exhausted_provider.calls == 2

    generic_provider = GenericProviderFailure()
    generic = build_planner(generic_provider)
    try:
        await generic.plan(user_goal="x")
        raise AssertionError("expected ProviderError")
    except ProviderError:
        # Generic provider failures are NOT structured-output retry candidates.
        assert generic_provider.calls == 1

    print("M7-B.3 PLANNER RETRY SMOKE PASSED")
    print("attempts:", result.diagnostics.attempts)
    print("retries :", result.diagnostics.retries)
    print("tokens  :", result.diagnostics.input_tokens + result.diagnostics.output_tokens)
    print("events  :", [event.value for event in events])


if __name__ == "__main__":
    asyncio.run(main())
