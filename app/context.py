from copy import deepcopy
from typing import Any
from dataclasses import dataclass
from app.memory import MemoryStore
import tiktoken
import json
_ENCODING = tiktoken.get_encoding("o200k_base")

class ContextBudgetError(RuntimeError):
    """当前必要上下文本身已经超过预算。"""

@dataclass(frozen=True)
class ContextPolicy:
    """控制一轮 LLM 请求可以使用多少上下文。"""

    max_input_tokens: int = 6000
    memory_budget_tokens: int = 1000

    def __post_init__(self) -> None:
        if self.max_input_tokens <= 0:
            raise ValueError("max_input_tokens 必须大于 0")

        if self.memory_budget_tokens < 0:
            raise ValueError("memory_budget_tokens 不能小于 0")

        if self.memory_budget_tokens >= self.max_input_tokens:
            raise ValueError(
                "memory_budget_tokens 必须小于 max_input_tokens"
            )

@dataclass(frozen=True)
class ContextStats:
    """记录本轮 Context Builder 做了什么。"""

    max_input_tokens: int
    estimated_input_tokens: int

    system_tokens: int
    memory_tokens: int
    history_tokens: int

    total_session_messages: int
    selected_session_messages: int
    dropped_session_messages: int

    total_memory_records: int
    selected_memory_records: int

@dataclass(frozen=True)
class ContextBuildResult:
    messages: list[dict[str, Any]]
    stats: ContextStats

def estimate_text_tokens(text: str) -> int:
    """估算普通文本的 Token 数。"""

    return len(_ENCODING.encode(text))

def estimate_message_tokens(message: dict[str, Any]) -> int:
    """
    估算一条完整 Message 的 Token 数。

    Tool Call 中包含 dict/list，因此不能只统计 content。
    这里将整个 Message 序列化后再进行 Token 估算。
    """

    serialized = json.dumps(
        message,
        ensure_ascii=False,
        separators=(",", ":"),
        default=str,
    )

    # 4 是近似的消息结构开销。
    return estimate_text_tokens(serialized) + 4

def estimate_messages_tokens(
    messages: list[dict[str, Any]],
) -> int:
    return sum(
        estimate_message_tokens(message)
        for message in messages
    )
def split_history_into_turns(
    messages: list[dict[str, Any]],
) -> list[list[dict[str, Any]]]:
    """
    将 History 划分为完整 User Turn。

    一个 Turn 从 user 开始，一直持续到下一个 user 出现之前。
    因此 tool_call、tool_result 和最终 assistant 不会被拆开。
    """

    turns: list[list[dict[str, Any]]] = []
    current_turn: list[dict[str, Any]] = []

    for message in messages:
        role = message.get("role")

        if role == "user":
            if current_turn:
                turns.append(current_turn)

            current_turn = [message]
            continue

        if current_turn:
            current_turn.append(message)
        else:
            # 理论上正常 Session 不应该出现这种孤立消息。
            # 这里仍然把它作为一个独立 block 保存。
            current_turn = [message]

    if current_turn:
        turns.append(current_turn)

    return turns

def build_memory_context(
    memory_store: MemoryStore | None,
    token_budget: int,
) -> tuple[str, int, int, int]:
    """
    在 Memory Token Budget 内选择长期记忆。

    返回：
        memory_text
        memory_tokens
        selected_records
        total_records
    """

    if memory_store is None or token_budget <= 0:
        return "", 0, 0, 0

    records = memory_store.list_records()

    if not records:
        return "", 0, 0, 0

    # 当前还没有语义检索，因此优先使用最近更新的 Memory。
    records = sorted(
        records,
        key=lambda record: record.updated_at,
        reverse=True,
    )

    header = "## Long-term Memory"
    selected_lines: list[str] = []

    current_tokens = estimate_text_tokens(header)

    for record in records:
        line = f"- [{record.key}] {record.value}"
        line_tokens = estimate_text_tokens("\n" + line)

        if current_tokens + line_tokens > token_budget:
            continue

        selected_lines.append(line)
        current_tokens += line_tokens

    if not selected_lines:
        return "", 0, 0, len(records)

    memory_text = "\n".join([header, *selected_lines])

    return (
        memory_text,
        estimate_text_tokens(memory_text),
        len(selected_lines),
        len(records),
    )

def build_runtime_context(
    session_messages: list[dict[str, Any]],
    memory_store: MemoryStore | None = None,
    policy: ContextPolicy | None = None,
) -> ContextBuildResult:
    """
    从完整 Session + Long-term Memory 中构建本轮 Runtime Context。

    重要原则：
    1. 不修改原始 Session。
    2. System Prompt 优先保留。
    3. Memory 有独立预算。
    4. Conversation 从最新 Turn 向前选择。
    5. 永远不拆开完整 User Turn。
    """

    policy = policy or ContextPolicy()
    copied_messages = deepcopy(session_messages)

    system_message: dict[str, Any] | None = None
    history_messages = copied_messages

    if copied_messages and copied_messages[0].get("role") == "system":
        system_message = copied_messages[0]
        history_messages = copied_messages[1:]

    original_system_tokens = 0

    if system_message is not None:
        original_system_tokens = estimate_message_tokens(system_message)

    if original_system_tokens >= policy.max_input_tokens:
        raise ContextBudgetError(
            "System Prompt 本身已经超过 Context Budget"
        )

    available_memory_tokens = min(
        policy.memory_budget_tokens,
        policy.max_input_tokens - original_system_tokens,
    )

    (
        memory_text,
        memory_tokens,
        selected_memory_records,
        total_memory_records,
    ) = build_memory_context(
        memory_store=memory_store,
        token_budget=available_memory_tokens,
    )

    runtime_prefix: list[dict[str, Any]] = []

    if system_message is not None:
        original_content = str(system_message.get("content", ""))

        if memory_text:
            system_message["content"] = (
                f"{original_content}\n\n{memory_text}"
            )

        runtime_prefix.append(system_message)

    elif memory_text:
        runtime_prefix.append(
            {
                "role": "system",
                "content": memory_text,
            }
        )

    prefix_tokens = estimate_messages_tokens(runtime_prefix)

    if prefix_tokens >= policy.max_input_tokens:
        raise ContextBudgetError(
            "System Prompt + Long-term Memory 已经占满 Context Budget"
        )

    history_budget = policy.max_input_tokens - prefix_tokens
    turns = split_history_into_turns(history_messages)

    selected_turns_reversed: list[list[dict[str, Any]]] = []
    selected_history_tokens = 0

    for turn in reversed(turns):
        turn_tokens = estimate_messages_tokens(turn)

        if selected_history_tokens + turn_tokens <= history_budget:
            selected_turns_reversed.append(turn)
            selected_history_tokens += turn_tokens
            continue

        # 如果连最新一轮都放不进去，不能偷偷删除当前用户请求。
        if not selected_turns_reversed:
            raise ContextBudgetError(
                "最新 User Turn 本身已经超过剩余 Context Budget"
            )

        # 保证 History 是连续的最近窗口。
        break

    selected_turns = list(reversed(selected_turns_reversed))

    selected_history = [
        message
        for turn in selected_turns
        for message in turn
    ]

    runtime_messages = [
        *runtime_prefix,
        *selected_history,
    ]

    selected_session_messages = len(selected_history)

    if system_message is not None:
        selected_session_messages += 1

    stats = ContextStats(
        max_input_tokens=policy.max_input_tokens,
        estimated_input_tokens=estimate_messages_tokens(runtime_messages),
        system_tokens=original_system_tokens,
        memory_tokens=memory_tokens,
        history_tokens=selected_history_tokens,
        total_session_messages=len(session_messages),
        selected_session_messages=selected_session_messages,
        dropped_session_messages=(
            len(session_messages) - selected_session_messages
        ),
        total_memory_records=total_memory_records,
        selected_memory_records=selected_memory_records,
    )

    return ContextBuildResult(
        messages=runtime_messages,
        stats=stats,
    )


def build_runtime_messages(
    session_messages: list[dict[str, Any]],
    memory_store: MemoryStore | None = None,
    policy: ContextPolicy | None = None,
) -> list[dict[str, Any]]:
    """
    兼容 Stage 9 的调用方式。

    真正逻辑已经集中到 build_runtime_context()。
    """

    return build_runtime_context(
        session_messages=session_messages,
        memory_store=memory_store,
        policy=policy,
    ).messages





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