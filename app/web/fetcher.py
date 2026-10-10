from __future__ import annotations

import asyncio
import ipaddress
import socket
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .models import FetchedPage


class WebFetchError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        error_type: str = "WEB_FETCH_ERROR",
        status_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.error_type = error_type
        self.status_code = status_code


@dataclass(frozen=True)
class FetchPolicy:
    timeout_seconds: float = 12.0
    max_response_bytes: int = 2_000_000
    max_text_chars: int = 20_000
    max_redirects: int = 5
    allowed_content_types: tuple[str, ...] = (
        "text/html",
        "text/plain",
        "application/xhtml+xml",
        "application/json",
    )


class _ReadableHTMLParser(HTMLParser):
    _SKIP_TAGS = {"script", "style", "noscript", "svg", "canvas"}
    _BLOCK_TAGS = {
        "article", "aside", "blockquote", "br", "div", "footer", "h1",
        "h2", "h3", "h4", "h5", "h6", "header", "li", "main", "nav",
        "ol", "p", "pre", "section", "table", "td", "th", "tr", "ul",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip_depth = 0
        self._in_title = False
        self._title_parts: list[str] = []
        self._parts: list[str] = []

    @property
    def title(self) -> str | None:
        value = " ".join("".join(self._title_parts).split())
        return value or None

    @property
    def text(self) -> str:
        raw = "".join(self._parts)
        lines = [" ".join(line.split()) for line in raw.splitlines()]
        return "\n".join(line for line in lines if line)

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        del attrs
        if tag in self._SKIP_TAGS:
            self._skip_depth += 1
            return
        if self._skip_depth:
            return
        if tag == "title":
            self._in_title = True
        if tag in self._BLOCK_TAGS:
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self._SKIP_TAGS and self._skip_depth:
            self._skip_depth -= 1
            return
        if self._skip_depth:
            return
        if tag == "title":
            self._in_title = False
        if tag in self._BLOCK_TAGS:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        if self._in_title:
            self._title_parts.append(data)
        self._parts.append(data)


class _SafeRedirectHandler(HTTPRedirectHandler):
    def __init__(self, validator, max_redirects: int) -> None:
        super().__init__()
        self._validator = validator
        self._max_redirects = max_redirects

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        count = int(req.headers.get("X-Nanobot-Redirect-Count", "0"))
        if count >= self._max_redirects:
            raise WebFetchError("网页重定向次数超过限制")

        absolute = urljoin(req.full_url, newurl)
        self._validator(absolute)
        redirected = super().redirect_request(
            req,
            fp,
            code,
            msg,
            headers,
            absolute,
        )
        if redirected is not None:
            redirected.add_header("X-Nanobot-Redirect-Count", str(count + 1))
        return redirected


class WebPageFetcher:
    def __init__(
        self,
        policy: FetchPolicy | None = None,
        *,
        user_agent: str = "nanobot-rebuild/0.16 (+local-agent-runtime)",
    ) -> None:
        self._policy = policy or FetchPolicy()
        self._user_agent = user_agent
        self._validate_policy()

    def _validate_policy(self) -> None:
        policy = self._policy
        if policy.timeout_seconds <= 0:
            raise ValueError("timeout_seconds 必须大于 0")
        if policy.max_response_bytes <= 0 or policy.max_text_chars <= 0:
            raise ValueError("网页大小限制必须大于 0")
        if policy.max_redirects < 0:
            raise ValueError("max_redirects 不能小于 0")

    async def fetch(self, url: str) -> FetchedPage:
        normalized = url.strip()
        self._validate_url(normalized)
        return await asyncio.to_thread(self._fetch_sync, normalized)

    @staticmethod
    def _is_forbidden_ip(value: str) -> bool:
        ip = ipaddress.ip_address(value)
        return any(
            (
                ip.is_private,
                ip.is_loopback,
                ip.is_link_local,
                ip.is_multicast,
                ip.is_reserved,
                ip.is_unspecified,
            )
        )

    def _validate_url(self, url: str) -> None:
        try:
            parsed = urlparse(url)
        except Exception as exc:
            raise WebFetchError(f"URL 解析失败: {exc}") from exc

        if parsed.scheme not in {"http", "https"}:
            raise WebFetchError("只允许 http/https URL")
        if not parsed.hostname:
            raise WebFetchError("URL 缺少 hostname")
        if parsed.username is not None or parsed.password is not None:
            raise WebFetchError("禁止带 username/password 的 URL")

        hostname = parsed.hostname.rstrip(".").lower()
        if hostname == "localhost" or hostname.endswith(".localhost"):
            raise WebFetchError("禁止访问 localhost")
        if hostname.endswith(".local"):
            raise WebFetchError("禁止访问 .local 主机")

        try:
            direct_ip = ipaddress.ip_address(hostname)
        except ValueError:
            direct_ip = None

        if direct_ip is not None:
            if self._is_forbidden_ip(str(direct_ip)):
                raise WebFetchError("禁止访问私有/本地/保留 IP")
            return

        try:
            infos = socket.getaddrinfo(
                hostname,
                parsed.port or (443 if parsed.scheme == "https" else 80),
                type=socket.SOCK_STREAM,
            )
        except OSError as exc:
            raise WebFetchError(f"DNS 解析失败: {hostname}: {exc}") from exc

        addresses = {info[4][0] for info in infos}
        if not addresses:
            raise WebFetchError(f"DNS 未返回地址: {hostname}")

        forbidden = [address for address in addresses if self._is_forbidden_ip(address)]
        if forbidden:
            raise WebFetchError(
                "目标域名解析到私有/本地/保留 IP，拒绝访问: "
                + ", ".join(sorted(forbidden))
            )

    def _fetch_sync(self, url: str) -> FetchedPage:
        redirect_handler = _SafeRedirectHandler(
            self._validate_url,
            self._policy.max_redirects,
        )
        opener = build_opener(redirect_handler)
        request = Request(
            url,
            headers={
                "User-Agent": self._user_agent,
                "Accept": (
                    "text/html,text/plain,application/xhtml+xml,"
                    "application/json;q=0.9,*/*;q=0.1"
                ),
                "Accept-Encoding": "identity",
            },
        )

        try:
            with opener.open(
                request,
                timeout=self._policy.timeout_seconds,
            ) as response:
                final_url = response.geturl()
                self._validate_url(final_url)

                raw_content_type = response.headers.get_content_type()
                content_type = raw_content_type.lower()
                if content_type not in self._policy.allowed_content_types:
                    raise WebFetchError(
                        f"不支持的 Content-Type: {content_type}"
                    )

                payload = response.read(self._policy.max_response_bytes + 1)
                if len(payload) > self._policy.max_response_bytes:
                    raise WebFetchError("网页响应超过大小限制")

                charset = response.headers.get_content_charset() or "utf-8"
                decoded = payload.decode(charset, errors="replace")

        except WebFetchError:
            raise
        except HTTPError as exc:
            raise WebFetchError(
                f"网页读取失败: HTTP {exc.code}: {exc.reason}",
                error_type=f"WEB_FETCH_HTTP_{exc.code}",
                status_code=exc.code,
            ) from exc
        except URLError as exc:
            raise WebFetchError(
                f"网页读取失败: URLError: {exc.reason}",
                error_type="WEB_FETCH_NETWORK_ERROR",
            ) from exc
        except TimeoutError as exc:
            raise WebFetchError(
                "网页读取失败: timeout",
                error_type="WEB_FETCH_TIMEOUT",
            ) from exc
        except Exception as exc:
            raise WebFetchError(
                f"网页读取失败: {type(exc).__name__}: {exc}",
                error_type="WEB_FETCH_ERROR",
            ) from exc

        if content_type in {"text/html", "application/xhtml+xml"}:
            parser = _ReadableHTMLParser()
            parser.feed(decoded)
            parser.close()
            title = parser.title
            text = parser.text
        else:
            title = None
            text = decoded

        text = text[: self._policy.max_text_chars]
        return FetchedPage(
            url=url,
            final_url=final_url,
            title=title,
            content_type=content_type,
            text=text,
        )
