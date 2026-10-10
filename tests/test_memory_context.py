from pathlib import Path

import pytest
from pydantic import BaseModel, ConfigDict

from app.agent import AgentRunner
from app.context import estimate_text_tokens
from app.memory import (
    MemoryAdmissionPolicy,
    MemoryCandidate,
    MemoryStore,
    build_memory_transcript,
)
from app.observation import (
    ToolObservationPolicy,
)
from app.providers import (
    FakeProvider,
    ProviderResponse,
    ToolCallRequest,
)
from app.tools.base import PydanticTool
from app.tools.registry import ToolRegistry


# ============================================================
# Test Tool
# ============================================================


class EmptyArguments(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )


class HugeOutputTool(PydanticTool):
    """
    测试专用 Tool。

    返回一个非常大的文本，
    用于验证 Raw Tool Result
    在进入 LLM Context 前是否被限制。
    """

    def __init__(
        self,
        content: str,
    ) -> None:
        self._content = content

    @property
    def name(self) -> str:
        return "huge_output"

    @property
    def description(self) -> str:
        return "返回一个很大的测试文本。"

    @property
    def argument_model(
        self,
    ) -> type[BaseModel]:
        return EmptyArguments

    async def execute(
        self,
        **kwargs,
    ) -> str:
        return self._content


# ============================================================
# 1. Memory transcript
# ============================================================


def test_memory_transcript_only_uses_user_messages():
    messages = [
        {
            "role": "user",
            "content": "我希望以后使用中文回答。",
        },
        {
            "role": "assistant",
            "content": "好的，我会用中文回答。",
        },
        {
            "role": "tool",
            "tool_call_id": "call-1",
            "content": "外部工具返回的数据。",
        },
        {
            "role": "user",
            "content": "我的长期目标是 Agent 开发。",
        },
    ]

    transcript = build_memory_transcript(
        messages
    )

    assert transcript == (
        "USER: 我希望以后使用中文回答。\n"
        "USER: 我的长期目标是 Agent 开发。"
    )

    assert "ASSISTANT" not in transcript
    assert "外部工具" not in transcript


# ============================================================
# 2. Memory Admission
# ============================================================


def test_memory_admission_rejects_secret():
    policy = MemoryAdmissionPolicy()

    candidates = [
        MemoryCandidate(
            key="user.language_preference",
            value="中文",
        ),
        MemoryCandidate(
            key="user.api_key",
            value="sk-1234567890abcdef",
        ),
        MemoryCandidate(
            key="user.note",
            value="password: hunter2",
        ),
    ]

    accepted = policy.filter(
        candidates
    )

    assert len(accepted) == 1

    assert accepted[0].key == (
        "user.language_preference"
    )

    assert accepted[0].value == "中文"


# ============================================================
# 3. Forget one Memory
# ============================================================


def test_memory_can_forget_single_key(
    tmp_path: Path,
):
    store = MemoryStore(
        workspace=tmp_path
    )

    changed = store.upsert_many(
        memories=[
            MemoryCandidate(
                key="user.name",
                value="张三",
            ),
            MemoryCandidate(
                key="user.career_goal",
                value="Agent开发",
            ),
        ],
        source_session="test-session",
    )

    assert changed == 2

    deleted = store.delete(
        "user.name"
    )

    assert deleted is True

    records = store.list_records()

    assert len(records) == 1
    assert records[0].key == (
        "user.career_goal"
    )
    assert records[0].value == (
        "Agent开发"
    )

    # 删除不存在的 Key
    deleted_again = store.delete(
        "user.name"
    )

    assert deleted_again is False


# ============================================================
# 4. Tool Observation Budget
# ============================================================


@pytest.mark.asyncio
async def test_large_tool_result_is_bounded_before_llm():
    raw_tool_output = (
        "BEGIN_MARKER\n"
        + ("very-long-tool-output " * 5000)
        + "\nEND_MARKER"
    )

    registry = ToolRegistry()

    registry.register(
        HugeOutputTool(
            raw_tool_output
        )
    )

    provider = FakeProvider(
        responses=[
            # 第一次 LLM 调用：
            # 请求调用 huge_output Tool
            ProviderResponse(
                content="",
                tool_calls=[
                    ToolCallRequest(
                        id="call-1",
                        name="huge_output",
                        arguments={},
                    )
                ],
            ),

            # 第二次 LLM 调用：
            # Tool Observation 已经进入 Context
            ProviderResponse(
                content="done",
                tool_calls=[],
            ),
        ]
    )

    runner = AgentRunner(
        provider=provider,
        tool_registry=registry,
        observation_policy=(
            ToolObservationPolicy(
                max_tokens=128,
            )
        ),
        concurrent_tools=False,
    )

    result = await runner.run(
        initial_messages=[
            {
                "role": "user",
                "content": (
                    "请调用 huge_output。"
                ),
            }
        ],
        task_text="请调用 huge_output。",
    )

    # --------------------------------------------------------
    # 1. Agent 确实执行了 Tool
    # --------------------------------------------------------

    assert len(result.tools_used) == 1

    record = result.tools_used[0]

    assert record.name == "huge_output"

    # Trace 中仍然保存 Raw Tool Result，
    # 不能因为 Observation 截断就丢掉原始结果。
    assert record.output == raw_tool_output

    assert (
        record.observation_truncated
        is True
    )

    assert (
        record.original_observation_tokens
        > 128
    )

    # --------------------------------------------------------
    # 2. 检查第二次发送给 LLM 的 Context
    # --------------------------------------------------------

    assert len(provider.calls) == 2

    second_call_messages = (
        provider.calls[1]["messages"]
    )

    tool_messages = [
        message
        for message
        in second_call_messages
        if message.get("role") == "tool"
    ]

    assert len(tool_messages) == 1

    observation_text = (
        tool_messages[0]["content"]
    )

    # LLM 看到的 Observation
    # 必须已经被限制到 Budget 内。
    assert (
        estimate_text_tokens(
            observation_text
        )
        <= 128
    )

    assert (
        "Tool output truncated"
        in observation_text
    )

    # Head + Tail 策略：
    # 开头和结尾都应该被保留。
    assert "BEGIN_MARKER" in (
        observation_text
    )

    assert "END_MARKER" in (
        observation_text
    )

    # Raw Result 明显大于
    # 真正送给 LLM 的 Observation。
    assert len(raw_tool_output) > len(
        observation_text
    )

    assert result.final_content == "done"