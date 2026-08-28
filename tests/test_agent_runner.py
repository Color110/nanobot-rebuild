from copy import deepcopy

from app.agent import AgentRunner
from app.conversation import add_message, create_conversation
from app.providers import FakeProvider, ProviderResponse
from app.tools.registry import ToolRegistry


async def test_runner_does_not_mutate_input_messages():
    provider = FakeProvider(
        responses=[
            ProviderResponse(
                content="你好。",
                tool_calls=[],
            )
        ]
    )

    runner = AgentRunner(
        provider=provider,
        tool_registry=ToolRegistry(),
    )

    messages = create_conversation()
    add_message(
        messages,
        role="user",
        content="你好",
    )

    original = deepcopy(messages)

    result = await runner.run(messages)

    assert messages == original

    assert len(result.messages) == len(original) + 1
    assert result.messages[-1] == {
        "role": "assistant",
        "content": "你好。",
    }