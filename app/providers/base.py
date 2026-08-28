from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any
import asyncio

@dataclass(frozen=True)
class ToolCallRequest:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class ProviderResponse:
    content: str
    tool_calls: list[ToolCallRequest]


class ProviderError(RuntimeError):
    """模型 Provider 调用或响应处理失败。"""


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