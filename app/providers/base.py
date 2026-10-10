from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ToolCallRequest:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class ProviderUsage:
    """Token usage reported by the upstream model provider."""

    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None


@dataclass(frozen=True)
class ProviderResponse:
    content: str
    tool_calls: list[ToolCallRequest]
    usage: ProviderUsage | None = None


class ProviderError(RuntimeError):
    """模型 Provider 调用或响应处理失败。"""


class StructuredOutputError(ProviderError):
    """
    Provider received a model response, but one structured field could not be
    decoded into the Runtime's expected representation.

    This is deliberately narrower than ProviderError: network/auth/rate-limit
    failures must not be mistaken for a retryable Planner formatting failure.
    """

    def __init__(
        self,
        message: str,
        *,
        stage: str,
        raw_value: str | None = None,
        usage: ProviderUsage | None = None,
    ) -> None:
        super().__init__(message)
        self.stage = stage
        self.raw_value = raw_value
        self.usage = usage


class LLMProvider(ABC):
    """所有 LLM Provider 必须遵守的统一接口。"""

    @property
    @abstractmethod
    def name(self) -> str:
        raise NotImplementedError

    @property
    @abstractmethod
    def model(self) -> str:
        raise NotImplementedError

    @abstractmethod
    async def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> ProviderResponse:
        raise NotImplementedError
