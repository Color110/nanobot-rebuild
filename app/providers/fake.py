from collections import deque
from copy import deepcopy
from typing import Any

from app.providers.base import (
    LLMProvider,
    ProviderResponse,
)


class FakeProvider(LLMProvider):
    """
    测试专用 Provider。

    不访问网络，而是按照预设顺序返回 ProviderResponse。
    """

    def __init__(
        self,
        responses: list[ProviderResponse],
        model: str = "fake-model",
    ) -> None:
        self._responses = deque(responses)
        self._model = model
        self.calls: list[dict[str, Any]] = []

    @property
    def name(self) -> str:
        return "fake"

    @property
    def model(self) -> str:
        return self._model

    async def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> ProviderResponse:
        self.calls.append(
            {
                "messages": deepcopy(messages),
                "tools": deepcopy(tools),
            }
        )

        if not self._responses:
            raise RuntimeError(
                "FakeProvider 没有剩余的预设响应"
            )

        return self._responses.popleft()