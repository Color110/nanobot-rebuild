from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.tools.base import PydanticTool, ToolExecutionError
from app.web import SearchProvider, SearchProviderError


class WebSearchArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(
        min_length=1,
        max_length=500,
        description=(
            "公开互联网搜索关键词或问题。建议包含关键实体、时间范围、"
            "产品名、错误码等能够缩小搜索范围的信息。"
        ),
    )
    max_results: int = Field(
        default=5,
        ge=1,
        le=10,
        description="最多返回的搜索结果数量。",
    )


class WebSearchTool(PydanticTool):
    def __init__(self, provider: SearchProvider) -> None:
        self._provider = provider

    @property
    def name(self) -> str:
        return "web_search"

    @property
    def description(self) -> str:
        return (
            "搜索公开互联网，返回候选页面的 title、url、snippet 和 source。"
            "适用于最新公开信息、官方资料、新闻、产品信息等本地知识库中"
            "可能不存在的内容。搜索结果只是线索；需要阅读正文时应继续调用 "
            "fetch_web_page。"
        )

    @property
    def argument_model(self) -> type[BaseModel]:
        return WebSearchArguments

    async def execute(self, **kwargs: Any) -> str:
        try:
            results = await self._provider.search(
                kwargs["query"],
                max_results=kwargs["max_results"],
            )
        except SearchProviderError as exc:
            raise ToolExecutionError(
                str(exc),
                error_type="WEB_SEARCH_ERROR",
            ) from exc

        payload = {
            "trust": "untrusted_external_content",
            "query": kwargs["query"],
            "provider": self._provider.name,
            "results": [
                {
                    "rank": index,
                    "title": result.title,
                    "url": result.url,
                    "snippet": result.snippet,
                    "source": result.source,
                }
                for index, result in enumerate(results, start=1)
            ],
        }
        return json.dumps(payload, ensure_ascii=False)
