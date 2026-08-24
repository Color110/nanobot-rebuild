from typing import Any

SYSTEM_PROMPT = (
    "你是 nanobot-rebuild 的 AI 助手。"
    "请准确、清晰地回答用户问题。"
    "当有合适的工具能够提供更可靠的结果时，优先使用工具。"
)

def create_conversation() -> list[dict[str, Any]]:
    """
    创建一个新的对话上下文。

    Returns:
        list[dict[str, Any]]: 一个空的对话上下文列表。
    """
    return [
        {
            "role": "system",
            "content": SYSTEM_PROMPT
        }
    ]

def add_message(
    messages: list[dict[str, Any]],
    role: str, 
    content: str
) -> None:
    """
    向对话上下文中添加一条消息。

    Args:
        message (list[dict[str, str]]): 对话上下文列表。
        role (str): 消息的角色（如 "user" 或 "assistant"）。
        content (str): 消息的内容。
    """
    messages.append({
        "role": role,
        "content": content
    })

def format_history(messages: list[dict[str, Any]]) -> str:
    """
    格式化对话历史记录为字符串。

    Args:
        history (list[dict[str, Any]]): 对话历史记录。

    Returns:
        str: 格式化后的对话历史记录字符串。
    """
    lines: list[str] = []
    for index,message in enumerate(messages):
        role = message.get("role", "unknown",)
        content = message.get("content","",)
        if(role == "assistant" and message.get("tool_call")):
            lines.append(
                f"{index}:"
                f"[assistant/tool_call]"
                f"{message['tool_calls']}"
            )
            continue
        if role == "tool":
            tool_call_id = message.get(
                "tool_call_id",
                "unknown",
            )

            lines.append(
                f"{index}: "
                f"[tool:{tool_call_id}] "
                f"{content}"
            )
            continue
        lines.append(
            f"{index}: [{role}] {content}"
        )
    return "\n".join(lines)