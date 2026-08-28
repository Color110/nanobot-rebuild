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
from app.providers.base import (
    LLMProvider,
    ProviderError,
    ProviderResponse,
    ToolCallRequest,
)
def test_agent_receives_tool_error(
    monkeypatch,
):

    responses=[
            ProviderResponse(
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
            ProviderResponse(
                content="无法完成该计算，因为除数不能为 0。",
                tool_calls=[],
            ),
        ]
        

from app.providers import (
    FakeProvider,
    ProviderResponse,
    ToolCallRequest,
)

async def test_agent_loop_executes_tool():
    provider = FakeProvider(
        responses=[
            ProviderResponse(
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
            ProviderResponse(
                content="12 × 8 = 96。",
                tool_calls=[],
            ),
        ]
    )

    registry = ToolRegistry()
    registry.register(CalculatorTool())

    messages = create_conversation()

    add_message(
        messages,
        role="user",
        content="计算12乘8",
    )

    result = await run_agent_turn(
        messages=messages,
        provider=provider,
        tool_registry=registry,
    )

    assert result.final_content == "12 × 8 = 96。"
    assert result.iterations == 2
    assert len(result.tools_used) == 1
    assert len(provider.calls) == 2