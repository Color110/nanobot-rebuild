from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from app.tools.base import ToolResult


@dataclass(frozen=True)
class WebFetchFailureGuardPolicy:
    repeated_failure_threshold: int = 2
    blocked_error_types: frozenset[str] = frozenset(
        {
            "WEB_FETCH_HTTP_401",
            "WEB_FETCH_HTTP_403",
            "WEB_FETCH_HTTP_429",
        }
    )

    def __post_init__(self) -> None:
        if self.repeated_failure_threshold < 1:
            raise ValueError("repeated_failure_threshold 必须 >= 1")


@dataclass(frozen=True)
class _FailureStreak:
    error_type: str
    count: int


class WebFetchFailureGuard:
    """Task-local repeated-failure guard for ``fetch_web_page``.

    Two invariants matter here:

    1. exact hostnames are isolated (``openai.com`` and
       ``grants.openai.com`` do not share state);
    2. fetches to the *same* hostname are serialized by ScopedToolRegistry so
       the failure streak is re-checked after every real network attempt.

    The guard tracks a consecutive streak. A successful fetch clears the
    streak for that hostname. A different blocked error type starts a new
    streak at 1 rather than accumulating unrelated failures forever.
    """

    def __init__(
        self,
        policy: WebFetchFailureGuardPolicy | None = None,
    ) -> None:
        self._policy = policy or WebFetchFailureGuardPolicy()
        self._streaks: dict[str, _FailureStreak] = {}
        self._lock = asyncio.Lock()

    @staticmethod
    def _hostname(arguments: dict[str, Any]) -> str | None:
        raw_url = arguments.get("url")
        if not isinstance(raw_url, str):
            return None
        try:
            hostname = urlparse(raw_url).hostname
        except Exception:
            return None
        return hostname.rstrip(".").lower() if hostname else None

    def serialization_key(
        self,
        *,
        name: str,
        arguments: dict[str, Any],
    ) -> str | None:
        """Serialize only fetches that target the exact same hostname."""
        if name != "fetch_web_page":
            return None
        hostname = self._hostname(arguments)
        if hostname is None:
            return None
        return f"fetch-host:{hostname}"

    async def before_execute(
        self,
        *,
        name: str,
        arguments: dict[str, Any],
    ) -> ToolResult | None:
        if name != "fetch_web_page":
            return None

        hostname = self._hostname(arguments)
        if hostname is None:
            return None

        async with self._lock:
            streak = self._streaks.get(hostname)
            if (
                streak is not None
                and streak.error_type in self._policy.blocked_error_types
                and streak.count >= self._policy.repeated_failure_threshold
            ):
                return ToolResult.error(
                    content=(
                        "Runtime 已阻止继续盲目抓取同一 hostname。"
                        f"hostname={hostname}, error_type={streak.error_type}, "
                        f"previous_failures={streak.count}. "
                        "本 Task 内请停止继续尝试该 hostname；优先改用其他"
                        "官方子域/来源，或基于 web_search 结果明确标注无法读取正文。"
                    ),
                    error_type="WEB_FETCH_REPEAT_BLOCKED",
                )
        return None

    async def after_execute(
        self,
        *,
        name: str,
        arguments: dict[str, Any],
        result: ToolResult,
    ) -> None:
        if name != "fetch_web_page":
            return

        hostname = self._hostname(arguments)
        if hostname is None:
            return

        async with self._lock:
            if not result.is_error:
                # A successful fetch proves the hostname is reachable again;
                # the consecutive access-failure streak must not leak forward.
                self._streaks.pop(hostname, None)
                return

            if result.error_type not in self._policy.blocked_error_types:
                # The policy only treats selected access-limit failures as one
                # consecutive streak. A different failure class breaks it.
                self._streaks.pop(hostname, None)
                return

            previous = self._streaks.get(hostname)
            if previous is not None and previous.error_type == result.error_type:
                self._streaks[hostname] = _FailureStreak(
                    error_type=result.error_type,
                    count=previous.count + 1,
                )
            else:
                self._streaks[hostname] = _FailureStreak(
                    error_type=result.error_type,
                    count=1,
                )

    def failure_count(self, hostname: str, error_type: str) -> int:
        normalized = hostname.rstrip(".").lower()
        streak = self._streaks.get(normalized)
        if streak is None or streak.error_type != error_type:
            return 0
        return streak.count
