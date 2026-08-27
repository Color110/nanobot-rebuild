from app.context import (
    build_runtime_messages,
)
from app.memory import (
    MemoryCandidate,
    MemoryStore,
)
import tiktoken

def test_memory_is_injected(
    tmp_path,
):

    store = MemoryStore(
        workspace=tmp_path
    )

    store.upsert_many(
        [
            MemoryCandidate(
                key="user.name",
                value="张三",
            )
        ],
        source_session="old",
    )

    session_messages = [
        {
            "role": "system",
            "content": "你是助手。",
        },
        {
            "role": "user",
            "content": "我叫什么？",
        },
    ]

    runtime = (
        build_runtime_messages(
            session_messages,
            memory_store=store,
        )
    )

    assert (
        "Long-term Memory"
        in runtime[0]["content"]
    )

    assert (
        "张三"
        in runtime[0]["content"]
    )


def test_session_is_not_mutated(
    tmp_path,
):

    store = MemoryStore(
        workspace=tmp_path
    )

    store.upsert_many(
        [
            MemoryCandidate(
                key="user.name",
                value="张三",
            )
        ],
        source_session="old",
    )

    session_messages = [
        {
            "role": "system",
            "content": "你是助手。",
        }
    ]

    build_runtime_messages(
        session_messages,
        memory_store=store,
    )

    assert (
        session_messages[0]["content"]
        == "你是助手。"
    )

import pytest

from app.context import (
    ContextBudgetError,
    ContextPolicy,
    build_runtime_context,
)


def test_old_history_is_trimmed():
    messages = [
        {
            "role": "system",
            "content": "你是助手。",
        },
        {
            "role": "user",
            "content": "OLD " * 2000,
        },
        {
            "role": "assistant",
            "content": "old answer",
        },
        {
            "role": "user",
            "content": "最新问题是什么？",
        },
    ]

    result = build_runtime_context(
        messages,
        policy=ContextPolicy(
            max_input_tokens=2000,
            memory_budget_tokens=0,
        ),
    )

    contents = [
        str(message.get("content", ""))
        for message in result.messages
    ]

    assert any("最新问题" in content for content in contents)
    assert not any("OLD OLD" in content for content in contents)

    assert result.stats.dropped_session_messages > 0
def test_tool_turn_is_kept_complete():
    messages = [
        {
            "role": "system",
            "content": "你是助手。",
        },
        {
            "role": "user",
            "content": "很久以前的问题 " * 1000,
        },
        {
            "role": "assistant",
            "content": "很久以前的回答",
        },
        {
            "role": "user",
            "content": "计算12乘8",
        },
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {
                        "name": "calculator",
                        "arguments": (
                            '{"left":12,'
                            '"operator":"*",'
                            '"right":8}'
                        ),
                    },
                }
            ],
        },
        {
            "role": "tool",
            "tool_call_id": "call_1",
            "content": "96",
        },
        {
            "role": "assistant",
            "content": "12乘8等于96。",
        },
    ]

    result = build_runtime_context(
        messages,
        policy=ContextPolicy(
            max_input_tokens=4000,
            memory_budget_tokens=0,
        ),
    )

    roles = [
        message["role"]
        for message in result.messages
    ]

    assert roles[-4:] == [
        "user",
        "assistant",
        "tool",
        "assistant",
    ]
def test_latest_turn_too_large():
    messages = [
        {
            "role": "system",
            "content": "你是助手。",
        },
        {
            "role": "user",
            "content": "非常长的当前请求 " * 5000,
        },
    ]

    with pytest.raises(
        ContextBudgetError,
        match="最新 User Turn",
    ):
        build_runtime_context(
            messages,
            policy=ContextPolicy(
                max_input_tokens=2000,
                memory_budget_tokens=0,
            ),
        )

from app.skills import SkillLoader
def test_explicit_skill_is_injected_into_runtime(tmp_path):
    skill_dir = tmp_path / "skills" / "file-math"
    skill_dir.mkdir(parents=True)

    (skill_dir / "SKILL.md").write_text(
        """---
name: file-math
description: 可靠执行文件数学任务
always: false
---

# File Math

必须先读取真实文件，再调用 calculator。
""",
        encoding="utf-8",
    )

    loader = SkillLoader(tmp_path)

    session_messages = [
        {
            "role": "system",
            "content": "你是助手。",
        },
        {
            "role": "user",
            "content": "$file-math 请执行任务",
        },
    ]

    result = build_runtime_context(
        session_messages=session_messages,
        skill_loader=loader,
        policy=ContextPolicy(
            max_input_tokens=1000,
            memory_budget_tokens=0,
            skills_budget_tokens=500,
        ),
    )

    system_content = result.messages[0]["content"]

    assert "Active Skills" in system_content
    assert "必须先读取真实文件" in system_content
    assert result.stats.active_skills == ("file-math",)

    # Runtime Context 构建不能污染 Session。
    assert session_messages[0]["content"] == "你是助手。"

def test_non_active_skill_only_exposes_summary(tmp_path):
    skill_dir = tmp_path / "skills" / "file-math"
    skill_dir.mkdir(parents=True)

    (skill_dir / "SKILL.md").write_text(
        """---
name: file-math
description: 可靠执行文件数学任务
always: false
---

# Secret Procedure

这里是只有激活后才应该加载的完整流程。
""",
        encoding="utf-8",
    )

    loader = SkillLoader(tmp_path)

    session_messages = [
        {
            "role": "system",
            "content": "你是助手。",
        },
        {
            "role": "user",
            "content": "TCP是什么？",
        },
    ]

    result = build_runtime_context(
        session_messages=session_messages,
        skill_loader=loader,
        policy=ContextPolicy(
            max_input_tokens=1000,
            memory_budget_tokens=0,
            skills_budget_tokens=500,
        ),
    )

    system_content = result.messages[0]["content"]

    assert "file-math" in system_content
    assert "可靠执行文件数学任务" in system_content
    assert "只有激活后才应该加载" not in system_content
    assert result.stats.active_skills == ()