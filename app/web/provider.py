from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from html.parser import HTMLParser
from urllib.parse import parse_qs, unquote, urlencode, urlparse
from urllib.request import Request, urlopen

from .models import SearchResult


class SearchProviderError(RuntimeError):
    pass


class SearchProvider(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        raise NotImplementedError

    @abstractmethod
    async def search(
        self,
        query: str,
        *,
        max_results: int = 5,
    ) -> list[SearchResult]:
        raise NotImplementedError


class FakeSearchProvider(SearchProvider):
    """Deterministic provider for tests/evals; never performs network I/O."""

    def __init__(
        self,
        results: list[SearchResult],
        *,
        provider_name: str = "fake-search",
    ) -> None:
        self._results = list(results)
        self._name = provider_name

    @property
    def name(self) -> str:
        return self._name

    async def search(
        self,
        query: str,
        *,
        max_results: int = 5,
    ) -> list[SearchResult]:
        del query
        return self._results[:max_results]


class _DuckDuckGoHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.results: list[SearchResult] = []
        self._current_url: str | None = None
        self._title_parts: list[str] = []
        self._snippet_parts: list[str] = []
        self._in_title = False
        self._in_snippet = False

    @staticmethod
    def _classes(attrs: list[tuple[str, str | None]]) -> set[str]:
        value = dict(attrs).get("class") or ""
        return {item for item in value.split() if item}

    @staticmethod
    def _normalize_result_url(raw_url: str) -> str:
        parsed = urlparse(raw_url)
        if raw_url.startswith("//"):
            parsed = urlparse("https:" + raw_url)
            raw_url = "https:" + raw_url

        if parsed.netloc.endswith("duckduckgo.com") and parsed.path.startswith("/l/"):
            target = parse_qs(parsed.query).get("uddg", [None])[0]
            if target:
                return unquote(target)

        return raw_url

    def _flush(self) -> None:
        if not self._current_url:
            return

        title = " ".join("".join(self._title_parts).split())
        snippet = " ".join("".join(self._snippet_parts).split())
        if not title:
            return

        host = urlparse(self._current_url).hostname
        self.results.append(
            SearchResult(
                title=title,
                url=self._current_url,
                snippet=snippet,
                source=host,
            )
        )
        self._current_url = None
        self._title_parts = []
        self._snippet_parts = []

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        classes = self._classes(attrs)
        attrs_dict = dict(attrs)

        if tag == "a" and "result__a" in classes:
            self._flush()
            href = attrs_dict.get("href")
            if href:
                self._current_url = self._normalize_result_url(href)
                self._title_parts = []
                self._snippet_parts = []
                self._in_title = True
            return

        if self._current_url and (
            "result__snippet" in classes
            or "result-snippet" in classes
        ):
            self._in_snippet = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._in_title:
            self._in_title = False
        if self._in_snippet and tag in {"a", "div", "span"}:
            self._in_snippet = False

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self._title_parts.append(data)
        elif self._in_snippet:
            self._snippet_parts.append(data)

    def close(self) -> None:
        super().close()
        self._flush()


class DuckDuckGoHtmlSearchProvider(SearchProvider):
    """
    Zero-key development search backend based on DuckDuckGo's HTML surface.

    This is intentionally isolated behind SearchProvider because HTML search
    surfaces are not stable APIs. It is suitable for local development/eval,
    while production can replace it with an official search API or MCP backend
    without changing WebSearchTool or AgentSpec permissions.
    """

    def __init__(
        self,
        *,
        timeout_seconds: float = 10.0,
        max_response_bytes: int = 1_500_000,
        user_agent: str = "nanobot-rebuild/0.16 (+local-agent-runtime)",
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds 必须大于 0")
        if max_response_bytes <= 0:
            raise ValueError("max_response_bytes 必须大于 0")

        self._timeout_seconds = timeout_seconds
        self._max_response_bytes = max_response_bytes
        self._user_agent = user_agent

    @property
    def name(self) -> str:
        return "duckduckgo-html"

    async def search(
        self,
        query: str,
        *,
        max_results: int = 5,
    ) -> list[SearchResult]:
        normalized = query.strip()
        if not normalized:
            raise SearchProviderError("搜索 query 不能为空")
        if not 1 <= max_results <= 10:
            raise SearchProviderError("max_results 必须在 1~10 之间")

        return await asyncio.to_thread(
            self._search_sync,
            normalized,
            max_results,
        )

    def _search_sync(
        self,
        query: str,
        max_results: int,
    ) -> list[SearchResult]:
        url = "https://html.duckduckgo.com/html/?" + urlencode({"q": query})
        request = Request(
            url,
            headers={
                "User-Agent": self._user_agent,
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Encoding": "identity",
            },
        )

        try:
            with urlopen(request, timeout=self._timeout_seconds) as response:
                payload = response.read(self._max_response_bytes + 1)
                if len(payload) > self._max_response_bytes:
                    raise SearchProviderError("搜索响应超过大小限制")

                charset = response.headers.get_content_charset() or "utf-8"
                html = payload.decode(charset, errors="replace")

        except SearchProviderError:
            raise
        except Exception as exc:
            raise SearchProviderError(
                f"Web Search 请求失败: {type(exc).__name__}: {exc}"
            ) from exc

        parser = _DuckDuckGoHTMLParser()
        parser.feed(html)
        parser.close()

        deduped: list[SearchResult] = []
        seen_urls: set[str] = set()
        for result in parser.results:
            if result.url in seen_urls:
                continue
            seen_urls.add(result.url)
            deduped.append(result)
            if len(deduped) >= max_results:
                break

        return deduped
