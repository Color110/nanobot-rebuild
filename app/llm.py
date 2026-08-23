import json
import os

from dataclasses import dataclass
from typing import Any

from openai import OpenAI


@dataclass
class ToolCallRequest:
    """
    LLM 请求调用某个 Tool。
    """

    id: str
    name: str
    arguments: dict[str, Any]

@dataclass
class LLMResult:
    """
    一次 LLM 调用的标准化结果。
    """

    content: str
    tool_calls: list[ToolCallRequest]

def parse_tool_arguments(
    raw_arguments: str,
) -> dict[str, Any]:
    """
    将模型返回的 JSON 字符串参数转换成 Python dict。
    """

    parsed = json.loads(
        raw_arguments or "{}"
    )

    if not isinstance(parsed, dict):
        raise ValueError(
            "Tool arguments 必须是 JSON object"
        )

    return parsed

def build_messages(user_message: str)-> list[dict[str,str]]:
    """
    Build a message for the OpenAI API.

    Args:
        user_message (str): The user's message.

    Returns:
        list[dict[str,str]]: A list of message dictionaries for the OpenAI API.
    """
    return [
        {"role": "user", "content": user_message}
    ]
def ask_llm(
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
    ) -> LLMResult:
    """
    Ask the language model a question, and return the response.

    Args:
        user_message (str): The user's message,
        tools (list[dict[str, Any]] | None): Optional list of tools that the model can use.


    Returns:
        LLMResult: The result from the language model.
    """
    api_key = os.getenv("LLM_API_KEY")
    base_url = os.getenv("LLM_BASE_URL")
    model = os.getenv("LLM_MODEL")
    if not api_key:
        raise RuntimeError(
            "LLM_API_KEY environment variable is not set."
            )
    if not model:
        raise RuntimeError(
            "LLM_MODEL environment variable is not set."
            )
    client = OpenAI(
        api_key=api_key, 
        base_url=base_url or None
        )
    
    request_kwargs : dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": 0.7,
    }

    if tools:
        request_kwargs["tools"] = tools

    response = client.chat.completions.create(
        **request_kwargs
        # model=model,
        # messages=messages,
        # temperature=0.7,
        # max_tokens=150
    )
    message = response.choices[0].message

    tool_calls: list[ToolCallRequest] = []
    for tool_call in (message.tool_calls or []):
        arguments = parse_tool_arguments(
            tool_call.function.arguments
        )
        tool_calls.append(
            ToolCallRequest(
                id=tool_call.id,
                name=tool_call.function.name,
                arguments=arguments
            )
        )
    return LLMResult(
        content=message.content or "",
        tool_calls=tool_calls
    )