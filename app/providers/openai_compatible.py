import json
import os
from typing import Any

from openai import AsyncOpenAI, OpenAIError

from app.providers.base import (
    LLMProvider,
    ProviderError,
    ProviderResponse,
    ProviderUsage,
    StructuredOutputError,
    ToolCallRequest,
)


def _usage_from_response(response: Any) -> ProviderUsage | None:
    upstream_usage = getattr(response, "usage", None)
    if upstream_usage is None:
        return None

    input_tokens = getattr(upstream_usage, "prompt_tokens", None)
    if input_tokens is None:
        input_tokens = getattr(upstream_usage, "input_tokens", None)

    output_tokens = getattr(upstream_usage, "completion_tokens", None)
    if output_tokens is None:
        output_tokens = getattr(upstream_usage, "output_tokens", None)

    total_tokens = getattr(upstream_usage, "total_tokens", None)
    if (
        total_tokens is None
        and input_tokens is not None
        and output_tokens is not None
    ):
        total_tokens = input_tokens + output_tokens

    return ProviderUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
    )


def parse_tool_arguments(
    raw_arguments: str,
    *,
    usage: ProviderUsage | None = None,
) -> dict[str, Any]:
    try:
        parsed = json.loads(raw_arguments or "{}")
    except json.JSONDecodeError as exc:
        preview = (raw_arguments or "")[:1200]
        raise StructuredOutputError(
            "模型返回了非法 Tool arguments JSON: "
            f"{preview!r}",
            stage="tool_arguments_json",
            raw_value=raw_arguments,
            usage=usage,
        ) from exc

    if not isinstance(parsed, dict):
        raise StructuredOutputError(
            "Tool arguments 必须是 JSON object",
            stage="tool_arguments_type",
            raw_value=raw_arguments,
            usage=usage,
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
        self._client = AsyncOpenAI(
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

    async def complete(
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
            response = await self._client.chat.completions.create(**request)
        except OpenAIError as exc:
            raise ProviderError(
                f"{self.name} 模型调用失败: {exc}"
            ) from exc

        # Capture usage before parsing tool arguments. If the model returned
        # malformed JSON, Planner retry still needs to account for this LLM
        # attempt instead of silently dropping its token cost.
        usage = _usage_from_response(response)

        message = response.choices[0].message
        tool_calls: list[ToolCallRequest] = []

        for tool_call in message.tool_calls or []:
            arguments = parse_tool_arguments(
                tool_call.function.arguments,
                usage=usage,
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
            usage=usage,
        )
