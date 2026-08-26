from copy import deepcopy
from typing import Any

from app.memory import MemoryStore


def build_runtime_messages(
    session_messages: list[
        dict[str, Any]
    ],
    memory_store: (
        MemoryStore | None
    ) = None,
) -> list[dict[str, Any]]:
    """
    根据持久化 Session State，
    构建真正发送给 LLM 的 Runtime Context。

    注意：
    不修改原始 Session messages。
    """

    runtime_messages = deepcopy(
        session_messages
    )

    if memory_store is None:
        return runtime_messages

    memory_context = (
        memory_store.render_context()
    )

    if not memory_context:
        return runtime_messages

    if (
        runtime_messages
        and runtime_messages[0].get(
            "role"
        ) == "system"
    ):

        original = (
            runtime_messages[0]
            .get(
                "content",
                "",
            )
        )

        runtime_messages[0][
            "content"
        ] = (
            f"{original}"
            f"\n\n"
            f"{memory_context}"
        )

    else:

        runtime_messages.insert(
            0,
            {
                "role": "system",
                "content": (
                    memory_context
                ),
            },
        )

    return runtime_messages