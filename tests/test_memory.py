from app.memory import (
    MemoryCandidate,
    MemoryStore,
)
from app.llm import (
    LLMResult,
    ToolCallRequest,
)
from app.memory import (
    extract_memories,
)

def test_memory_upsert(
    tmp_path,
):

    store = MemoryStore(
        workspace=tmp_path
    )

    changed = store.upsert_many(
        [
            MemoryCandidate(
                key="user.name",
                value="张三",
            )
        ],
        source_session="session-a",
    )

    assert changed == 1

    records = (
        store.list_records()
    )

    assert len(records) == 1

    assert (
        records[0].key
        == "user.name"
    )

    assert (
        records[0].value
        == "张三"
    )


def test_memory_update_same_key(
    tmp_path,
):

    store = MemoryStore(
        workspace=tmp_path
    )

    store.upsert_many(
        [
            MemoryCandidate(
                key=(
                    "user."
                    "language_preference"
                ),
                value="中文",
            )
        ],
        source_session="a",
    )

    store.upsert_many(
        [
            MemoryCandidate(
                key=(
                    "user."
                    "language_preference"
                ),
                value="中文为主，必要时英文",
            )
        ],
        source_session="b",
    )

    records = (
        store.list_records()
    )

    assert len(records) == 1

    assert (
        records[0].value
        == "中文为主，必要时英文"
    )

    assert (
        records[0].source_session
        == "b"
    )


def test_memory_context(
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
            ),
            MemoryCandidate(
                key=(
                    "user."
                    "language_preference"
                ),
                value="用户偏好中文",
            ),
        ],
        source_session="demo",
    )

    context = (
        store.render_context()
    )

    assert (
        "Long-term Memory"
        in context
    )

    assert (
        "user.name"
        in context
    )

    assert "张三" in context


def test_memory_clear(
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
        source_session="demo",
    )

    store.clear()

    assert (
        store.list_records()
        == []
    )

def test_extract_memories(
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
                    id="memory_1",
                    name="save_memories",
                    arguments={
                        "memories": [
                            {
                                "key": (
                                    "user.name"
                                ),
                                "value": "张三",
                            },
                            {
                                "key": (
                                    "user."
                                    "language_preference"
                                ),
                                "value": (
                                    "用户偏好中文回答"
                                ),
                            },
                        ]
                    },
                )
            ],
        )

    monkeypatch.setattr(
        "app.memory.ask_llm",
        fake_ask_llm,
    )

    messages = [
        {
            "role": "system",
            "content": "system",
        },
        {
            "role": "user",
            "content": (
                "我叫张三，"
                "以后尽量使用中文回答。"
            ),
        },
        {
            "role": "assistant",
            "content": "好的。",
        },
    ]

    memories = (
        extract_memories(
            messages
        )
    )

    assert len(memories) == 2

    assert (
        memories[0].key
        == "user.name"
    )