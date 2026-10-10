import asyncio

import pytest
from pydantic import BaseModel, ConfigDict

from app.orchestration.capabilities import ScopedToolRegistry
from app.orchestration.executor import (
    SubAgentConfigurationError,
    SubAgentExecutor,
)
from app.orchestration.models import (
    AgentSpec,
    RuntimeTask,
    TaskBudget,
    TaskStatus,
)
from app.providers import (
    FakeProvider,
    LLMProvider,
    ProviderResponse,
    ToolCallRequest,
)
from app.tools.base import PydanticTool
from app.tools.registry import ToolRegistry


class EmptyArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")


class NamedTool(PydanticTool):
    def __init__(self, name: str, output: str) -> None:
        self._name = name
        self._output = output

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return f"test tool {self._name}"

    @property
    def argument_model(self) -> type[BaseModel]:
        return EmptyArguments

    async def execute(self, **kwargs) -> str:
        return self._output


class SlowProvider(LLMProvider):
    @property
    def name(self) -> str:
        return "slow"

    @property
    def model(self) -> str:
        return "slow-model"

    async def complete(self, messages, tools=None) -> ProviderResponse:
        await asyncio.sleep(0.2)
        return ProviderResponse(content="late", tool_calls=[])


def build_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(NamedTool("search_web", "SEARCH_OK"))
    registry.register(NamedTool("delete_database", "DELETE_OK"))
    return registry


def build_spec() -> AgentSpec:
    return AgentSpec(
        agent_type="researcher",
        system_prompt="You are a research sub-agent.",
        allowed_tools=frozenset({"search_web"}),
        budget=TaskBudget(
            max_iterations=4,
            timeout_seconds=2.0,
            max_input_tokens=2000,
        ),
    )


def build_task(*, timeout_seconds: float = 2.0) -> RuntimeTask:
    return RuntimeTask(
        workflow_id="wf_test",
        task_id="research_company",
        objective="Research the company.",
        agent_type="researcher",
        granted_tools=("search_web",),
        budget=TaskBudget(
            max_iterations=4,
            timeout_seconds=timeout_seconds,
            max_input_tokens=2000,
        ),
    )


def test_scoped_registry_only_exposes_granted_tools():
    global_registry = build_registry()
    scoped = ScopedToolRegistry(
        parent=global_registry,
        allowed_tools={"search_web"},
    )

    assert scoped.names() == ["search_web"]

    schemas = scoped.get_definitions()
    names = [item["function"]["name"] for item in schemas]
    assert names == ["search_web"]


@pytest.mark.asyncio
async def test_scoped_registry_denies_hidden_tool_execution():
    global_registry = build_registry()
    scoped = ScopedToolRegistry(
        parent=global_registry,
        allowed_tools={"search_web"},
    )

    result = await scoped.execute(
        name="delete_database",
        arguments={},
    )

    assert result.is_error is True
    assert result.error_type == "TOOL_NOT_ALLOWED"
    assert "DELETE_OK" not in result.content


@pytest.mark.asyncio
async def test_subagent_executor_reuses_agent_runner_with_scoped_tools():
    provider = FakeProvider(
        responses=[
            ProviderResponse(
                content="",
                tool_calls=[
                    ToolCallRequest(
                        id="call-1",
                        name="search_web",
                        arguments={},
                    )
                ],
            ),
            ProviderResponse(
                content="research complete",
                tool_calls=[],
            ),
        ]
    )

    executor = SubAgentExecutor(
        provider=provider,
        global_tool_registry=build_registry(),
        agent_specs={"researcher": build_spec()},
        concurrent_tools=False,
    )

    result = await executor.execute(build_task())

    assert result.status == TaskStatus.SUCCEEDED
    assert result.data["final_content"] == "research complete"
    assert result.metrics.llm_calls == 2
    assert result.metrics.tool_calls == 1

    # The LLM can see search_web but not the globally registered dangerous tool.
    exposed = [
        item["function"]["name"]
        for item in provider.calls[0]["tools"]
    ]
    assert exposed == ["search_web"]
    assert "delete_database" not in exposed

    # Child context is freshly built around the task contract.
    first_messages = provider.calls[0]["messages"]
    serialized = str(first_messages)
    assert "Research the company." in serialized
    assert "SubAgent Runtime Contract" in serialized


@pytest.mark.asyncio
async def test_executor_defense_in_depth_rejects_spec_mismatch():
    task = RuntimeTask(
        workflow_id="wf_test",
        task_id="bad_task",
        objective="Do something dangerous.",
        agent_type="researcher",
        granted_tools=("delete_database",),
        budget=TaskBudget(
            max_iterations=2,
            timeout_seconds=1.0,
            max_input_tokens=1000,
        ),
    )

    executor = SubAgentExecutor(
        provider=FakeProvider(
            responses=[
                ProviderResponse(content="never", tool_calls=[]),
            ]
        ),
        global_tool_registry=build_registry(),
        agent_specs={"researcher": build_spec()},
    )

    with pytest.raises(SubAgentConfigurationError):
        await executor.execute(task)


@pytest.mark.asyncio
async def test_executor_returns_structured_timeout_result():
    executor = SubAgentExecutor(
        provider=SlowProvider(),
        global_tool_registry=build_registry(),
        agent_specs={"researcher": build_spec()},
    )

    result = await executor.execute(
        build_task(timeout_seconds=0.05)
    )

    assert result.status == TaskStatus.TIMED_OUT
    assert result.error is not None
    assert result.error.code == "TASK_TIMEOUT"
    assert result.error.ambiguous_side_effect is True
