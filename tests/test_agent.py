from app.llm import LLMResult, ToolCallRequest, ask_llm
from app.tools.registry import ToolRegistry
from app.tools.calculator import (
    CalculatorTool,
)
from app.conversation import (
    add_message,
    create_conversation,
    format_history,
)
from app.agent import run_agent_turn

def test_agent_receives_tool_error(
    monkeypatch,
):

    responses = [
        LLMResult(
            content="",
            tool_calls=[
                ToolCallRequest(
                    id="call_error",
                    name="calculator",
                    arguments={
                        "left": 10,
                        "operator": "/",
                        "right": 0,
                    },
                )
            ],
        ),
        LLMResult(
            content=(
                "无法完成该计算，"
                "因为除数不能为 0。"
            ),
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

    registry = ToolRegistry()

    registry.register(
        CalculatorTool()
    )

    messages = create_conversation()

    add_message(
        messages,
        "user",
        "10除以0",
    )

    result = run_agent_turn(
        messages,
        tool_registry=registry,
    )

    assert len(
        result.tools_used
    ) == 1

    record = (
        result.tools_used[0]
    )

    assert record.is_error is True

    assert (
        record.error_type
        == "EXECUTION_ERROR"
    )

    tool_message = messages[3]

    assert (
        "ToolError"
        in tool_message["content"]
    )

    assert (
        result.final_content
        == "无法完成该计算，因为除数不能为 0。"
    )