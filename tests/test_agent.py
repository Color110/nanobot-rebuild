from app.tools.calculator import (
    CalculatorTool,
)
from app.tools.registry import (
    ToolRegistry,
)
from app.agent import (
    run_agent_turn,
    LLMResult,
    ToolCallRequest,
)
from app.conversation import (
    add_message,
    create_conversation,
)
from typing import Any
from pathlib import Path


registry = ToolRegistry()

registry.register(
    CalculatorTool()
)
import pytest

def test_agent_loop_executes_tool(
    monkeypatch,
):
    responses = [
        LLMResult(
            content="",
            tool_calls=[
                ToolCallRequest(
                    id="call_1",
                    name="calculator",
                    arguments={
                        "left": 12,
                        "operator": "*",
                        "right": 8,
                    },
                )
            ],
        ),
        LLMResult(
            content="12 × 8 = 96。",
            tool_calls=[],
        ),
    ]

    def fake_ask_llm(
        messages,
        tools=None,
    ):
        return responses.pop(0)

    monkeypatch.setattr(
        "app.agent.ask_llm",
        fake_ask_llm,
    )

    messages = create_conversation()

    add_message(
        messages,
        role="user",
        content="计算12乘8",
    )

    result = run_agent_turn(
        messages,tool_registry=registry
    )

    assert result.final_content == (
        "12 × 8 = 96。"
    )

    assert result.iterations == 2

    assert len(result.tools_used) == 1

    assert (
        result.tools_used[0].name
        == "calculator"
    )

    assert (
        result.tools_used[0].output
        == "96"
    )

    roles = [
        message["role"]
        for message in messages
    ]

    assert roles == [
        "system",
        "user",
        "assistant",
        "tool",
        "assistant",
    ]


def test_tool_call_id_is_preserved(
    monkeypatch,
):
    responses = [
        LLMResult(
            content="",
            tool_calls=[
                ToolCallRequest(
                    id="call_xyz",
                    name="calculator",
                    arguments={
                        "left": 10,
                        "operator": "+",
                        "right": 5,
                    },
                )
            ],
        ),
        LLMResult(
            content="结果是15。",
            tool_calls=[],
        ),
    ]

    def fake_ask_llm(
        messages,
        tools=None,
    ):
        return responses.pop(0)

    monkeypatch.setattr(
        "app.agent.ask_llm",
        fake_ask_llm,
    )

    messages = create_conversation()

    add_message(
        messages,
        "user",
        "10加5",
    )

    run_agent_turn(messages,tool_registry=registry)

    assistant_tool_message = messages[2]
    tool_result_message = messages[3]

    assert (
        assistant_tool_message
        ["tool_calls"][0]["id"]
        == "call_xyz"
    )

    assert (
        tool_result_message
        ["tool_call_id"]
        == "call_xyz"
    )


def test_agent_max_iterations(
    monkeypatch,
):
    def fake_ask_llm(
        messages,
        tools=None,
    ):
        return LLMResult(
            content="",
            tool_calls=[
                ToolCallRequest(
                    id="call_repeat",
                    name="calculator",
                    arguments={
                        "left": 1,
                        "operator": "+",
                        "right": 1,
                    },
                )
            ],
        )

    monkeypatch.setattr(
        "app.agent.ask_llm",
        fake_ask_llm,
    )

    messages = create_conversation()

    add_message(
        messages,
        "user",
        "一直算",
    )

    with pytest.raises(
        RuntimeError,
        match="max iterations",
    ):
        run_agent_turn(
            messages,
            tool_registry=registry,
            max_iterations=2,
        )