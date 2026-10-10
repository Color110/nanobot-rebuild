from __future__ import annotations

import asyncio
import json
import os
from typing import Any
from urllib import error, request

from app.web.models import SearchResult
from app.web.provider import (
    SearchProvider,
    SearchProviderError,
)


class BochaSearchProvider(SearchProvider):
    """
    博查 Web Search API Provider。

    这一层只负责：
        query
        -> Bocha HTTP API
        -> list[SearchResult]

    Agent / ToolRegistry / Multi-Agent 不感知博查 API 的具体格式。
    """

    DEFAULT_ENDPOINT = "https://api.bochaai.com/v1/web-search"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        endpoint: str = DEFAULT_ENDPOINT,
        timeout_seconds: float = 15.0,
        freshness: str = "noLimit",
        include_summary: bool = True,
    ) -> None:
        resolved_api_key = (
            api_key
            or os.getenv("BOCHA_API_KEY")
        )

        if not resolved_api_key:
            raise ValueError(
                "缺少博查 API Key。"
                "请传入 api_key，或设置环境变量 BOCHA_API_KEY。"
            )

        if timeout_seconds <= 0:
            raise ValueError(
                "timeout_seconds 必须大于 0"
            )

        self._api_key = resolved_api_key
        self._endpoint = endpoint
        self._timeout_seconds = timeout_seconds
        self._freshness = freshness
        self._include_summary = include_summary

    @property
    def name(self) -> str:
        return "bocha"

    async def search(
        self,
        query: str,
        *,
        max_results: int = 5,
    ) -> list[SearchResult]:
        normalized_query = query.strip()

        if not normalized_query:
            raise SearchProviderError(
                "搜索 query 不能为空"
            )

        if not 1 <= max_results <= 10:
            raise SearchProviderError(
                "max_results 必须位于 1~10"
            )

        # urllib 是同步 API。
        # SearchProvider.search() 是 async，
        # 所以把阻塞网络请求放进线程池，
        # 避免阻塞整个 asyncio Event Loop。
        return await asyncio.to_thread(
            self._search_sync,
            normalized_query,
            max_results,
        )

    def _search_sync(
        self,
        query: str,
        max_results: int,
    ) -> list[SearchResult]:
        payload = {
            "query": query,
            "freshness": self._freshness,
            "summary": self._include_summary,
            "count": max_results,
        }

        body = json.dumps(
            payload,
            ensure_ascii=False,
        ).encode("utf-8")

        http_request = request.Request(
            self._endpoint,
            data=body,
            method="POST",
            headers={
                "Authorization": (
                    f"Bearer {self._api_key}"
                ),
                "Content-Type": (
                    "application/json"
                ),
                "Accept": (
                    "application/json"
                ),
            },
        )

        try:
            with request.urlopen(
                http_request,
                timeout=self._timeout_seconds,
            ) as response:
                raw_body = response.read()

        except error.HTTPError as exc:
            detail = self._read_http_error(exc)

            raise SearchProviderError(
                "博查 Web Search API "
                f"HTTP {exc.code}: {detail}"
            ) from exc

        except error.URLError as exc:
            raise SearchProviderError(
                "无法连接博查 Web Search API: "
                f"{exc.reason}"
            ) from exc

        except TimeoutError as exc:
            raise SearchProviderError(
                "博查 Web Search API 请求超时"
            ) from exc

        try:
            data = json.loads(
                raw_body.decode("utf-8")
            )
        except (
            UnicodeDecodeError,
            json.JSONDecodeError,
        ) as exc:
            raise SearchProviderError(
                "博查 Web Search API "
                "返回了无法解析的 JSON"
            ) from exc

        return self._parse_results(
            data,
            max_results=max_results,
        )

    @staticmethod
    def _read_http_error(
        exc: error.HTTPError,
    ) -> str:
        try:
            raw = exc.read()

            if not raw:
                return str(exc.reason)

            return raw.decode(
                "utf-8",
                errors="replace",
            )[:2000]

        except Exception:
            return str(exc.reason)

    @staticmethod
    def _parse_results(
        data: dict[str, Any],
        *,
        max_results: int,
    ) -> list[SearchResult]:
        """
        博查常见响应结构：

        {
            "code": 200,
            "data": {
                "webPages": {
                    "value": [
                        {
                            "name": "...",
                            "url": "...",
                            "snippet": "...",
                            "summary": "...",
                            "siteName": "...",
                            ...
                        }
                    ]
                }
            }
        }
        """

        code = data.get("code")

        if code not in (None, 200):
            message = (
                data.get("msg")
                or data.get("message")
                or "unknown error"
            )

            raise SearchProviderError(
                "博查 Web Search API "
                f"业务错误 code={code}: "
                f"{message}"
            )

        response_data = data.get("data")

        if not isinstance(
            response_data,
            dict,
        ):
            raise SearchProviderError(
                "博查响应缺少 data 对象"
            )

        web_pages = response_data.get(
            "webPages"
        )

        if not isinstance(
            web_pages,
            dict,
        ):
            # 没搜到网页时，有的 API
            # 可能直接不给 webPages。
            return []

        values = web_pages.get(
            "value",
            [],
        )

        if not isinstance(
            values,
            list,
        ):
            raise SearchProviderError(
                "博查响应中的 "
                "data.webPages.value "
                "不是数组"
            )

        results: list[SearchResult] = []

        for item in values:
            if not isinstance(
                item,
                dict,
            ):
                continue

            url = str(
                item.get("url") or ""
            ).strip()

            if not url:
                continue

            title = str(
                item.get("name")
                or item.get("title")
                or url
            ).strip()

            # 如果请求 summary=true，
            # 优先采用 summary；
            # 没有时退回 snippet。
            snippet = str(
                item.get("snippet")
                or item.get("summary")
                or ""
            ).strip()

            source = str(
                item.get("siteName")
                or ""
            ).strip() or None

            results.append(
                SearchResult(
                    title=title,
                    url=url,
                    snippet=snippet,
                    source=source,
                )
            )

            if len(results) >= max_results:
                break

        return results