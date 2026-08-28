from pathlib import Path

from app.agent import AgentRunner
from app.agent_loop import AgentLoop
from app.providers import FakeProvider, ProviderResponse
from app.session import SessionManager
from app.tools.registry import ToolRegistry


async def test_agent_loop_commits_successful_turn(
    tmp_path: Path,
):
    provider = FakeProvider(
        responses=[
            ProviderResponse(
                content="你好张三。",
                tool_calls=[],
            )
        ]
    )

    runner = AgentRunner(
        provider=provider,
        tool_registry=ToolRegistry(),
    )

    session_manager = SessionManager(
        tmp_path / "sessions"
    )

    loop = AgentLoop(
        runner=runner,
        session_manager=session_manager,
    )

    result = await loop.process_user_message(
        session_id="demo",
        content="我叫张三",
    )

    assert result.final_content == "你好张三。"

    restored = session_manager.load("demo")

    assert restored is not None

    assert restored.messages[-2] == {
        "role": "user",
        "content": "我叫张三",
    }

    assert restored.messages[-1] == {
        "role": "assistant",
        "content": "你好张三。",
    }

import pytest

from app.conversation import add_message


async def test_agent_loop_does_not_commit_failed_turn(
    tmp_path: Path,
):
    session_manager = SessionManager(
        tmp_path / "sessions"
    )

    session = session_manager.get_or_create("demo")

    add_message(
        session.messages,
        role="user",
        content="旧问题",
    )

    add_message(
        session.messages,
        role="assistant",
        content="旧回答",
    )

    session_manager.save(session)

    original_messages = list(session.messages)

    # 没有预设 Response，
    # 第一次 Provider 调用就会失败。
    provider = FakeProvider(responses=[])

    runner = AgentRunner(
        provider=provider,
        tool_registry=ToolRegistry(),
    )

    loop = AgentLoop(
        runner=runner,
        session_manager=session_manager,
    )

    with pytest.raises(
        RuntimeError,
        match="没有剩余",
    ):
        await loop.process_user_message(
            session_id="demo",
            content="这是一条失败的新请求",
        )

    restored = session_manager.load("demo")

    assert restored is not None
    assert restored.messages == original_messages