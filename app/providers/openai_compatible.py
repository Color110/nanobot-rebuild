import json
import os
from typing import Any

from openai import OpenAI, OpenAIError

from app.providers.base import (
    LLMProvider,
    ProviderError,
    ProviderResponse,
    ToolCallRequest,
)


def parse_tool_arguments(raw_arguments: str) -> dict[str, Any]:
    try:
        parsed = json.loads(raw_arguments or "{}")
    except json.JSONDecodeError as exc:
        raise ProviderError(
            f"模型返回了非法 Tool arguments JSON: {raw_arguments!r}"
        ) from exc

    if not isinstance(parsed, dict):
        raise ProviderError(
            "Tool arguments 必须是 JSON object"
        )

    return parsed


class OpenAICompatibleProvider(LLMProvider):
    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("api_key 不能为空")

        if not model:
            raise ValueError("model 不能为空")

        self._model = model
        self._client = OpenAI(
            api_key=api_key,
            base_url=base_url or None,
        )

    @property
    def name(self) -> str:
        return "openai-compatible"

    @property
    def model(self) -> str:
        return self._model

    @classmethod
    def from_env(cls) -> "OpenAICompatibleProvider":
        api_key = os.getenv("LLM_API_KEY")
        base_url = os.getenv("LLM_BASE_URL")
        model = os.getenv("LLM_MODEL")

        if not api_key:
            raise RuntimeError("缺少环境变量 LLM_API_KEY")

        if not model:
            raise RuntimeError("缺少环境变量 LLM_MODEL")

        return cls(
            api_key=api_key,
            base_url=base_url,
            model=model,
        )

    def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> ProviderResponse:
        request: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
        }

        if tools:
            request["tools"] = tools

        try:
            response = self._client.chat.completions.create(**request)
        except OpenAIError as exc:
            raise ProviderError(
                f"{self.name} 模型调用失败: {exc}"
            ) from exc

        message = response.choices[0].message
        tool_calls: list[ToolCallRequest] = []

        for tool_call in message.tool_calls or []:
            arguments = parse_tool_arguments(
                tool_call.function.arguments
            )

            tool_calls.append(
                ToolCallRequest(
                    id=tool_call.id,
                    name=tool_call.function.name,
                    arguments=arguments,
                )
            )

        return ProviderResponse(
            content=message.content or "",
            tool_calls=tool_calls,
        )