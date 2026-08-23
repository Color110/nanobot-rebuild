SYSTEM_PROMPT =(
    "你是nanobot-rebuild，一个由开源模型驱动的聊天机器人。"
    "你将根据用户的输入提供有帮助、准确清晰和相关的回答。"
)
def create_conversation() -> list[dict[str, str]]:
    """
    创建一个新的对话上下文。

    Returns:
        list[dict[str, str]]: 一个空的对话上下文列表。
    """
    return [
        {
            "role": "system",
            "content": SYSTEM_PROMPT
        }
    ]

def add_message(
    messages: list[dict[str, str]],
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

def format_history(messages: list[dict[str, str]]) -> str:
    """
    格式化对话历史记录为字符串。

    Args:
        history (list[dict[str, str]]): 对话历史记录。

    Returns:
        str: 格式化后的对话历史记录字符串。
    """
    lines: list[str] = []
    for index,message in enumerate(messages):
        role = message["role"]
        content = message["content"]
        lines.append(
            f"{index}: [{role}] {content}"
        )
    return "\n".join(lines)