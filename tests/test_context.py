from app.context import (
    build_runtime_messages,
)
from app.memory import (
    MemoryCandidate,
    MemoryStore,
)


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