from __future__ import annotations

import asyncio
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field

from app.orchestration.capabilities import ScopedToolRegistry
from app.tools.base import PydanticTool, ToolExecutionError
from app.tools.registry import ToolRegistry
from app.web.failure_guard import WebFetchFailureGuard


class _Args(BaseModel):
    model_config = ConfigDict(extra="forbid")
    url: str = Field(min_length=1)


class _FakeFetchTool(PydanticTool):
    def __init__(self) -> None:
        self.backend_calls: list[str] = []

    @property
    def name(self) -> str:
        return "fetch_web_page"

    @property
    def description(self) -> str:
        return "fake fetch for same-host serialization smoke"

    @property
    def argument_model(self) -> type[BaseModel]:
        return _Args

    async def execute(self, **kwargs):
        url = kwargs["url"]
        self.backend_calls.append(url)
        await asyncio.sleep(0.03)
        parsed = urlparse(url)

        if parsed.hostname == "openai.com":
            raise ToolExecutionError(
                "HTTP 403",
                error_type="WEB_FETCH_HTTP_403",
            )

        if parsed.path.startswith("/fail"):
            raise ToolExecutionError(
                "HTTP 403",
                error_type="WEB_FETCH_HTTP_403",
            )

        return "OK"


async def main() -> None:
    parent = ToolRegistry()
    fake = _FakeFetchTool()
    parent.register(fake)

    guard = WebFetchFailureGuard()
    scoped = ScopedToolRegistry(
        parent=parent,
        allowed_tools={"fetch_web_page"},
        guards=(guard,),
    )

    # Three same-host calls are started concurrently. Only the first two are
    # allowed to reach the backend. The third must re-check the streak after
    # waiting for the same-host lock and be blocked before real execution.
    same_host = await asyncio.gather(
        scoped.execute("fetch_web_page", {"url": "https://openai.com/a"}),
        scoped.execute("fetch_web_page", {"url": "https://openai.com/b"}),
        scoped.execute("fetch_web_page", {"url": "https://openai.com/c"}),
    )

    assert [r.error_type for r in same_host].count("WEB_FETCH_HTTP_403") == 2
    assert [r.error_type for r in same_host].count("WEB_FETCH_REPEAT_BLOCKED") == 1
    assert sum("openai.com" in url for url in fake.backend_calls) == 2

    # A different hostname stays independent and can still execute.
    grants = await scoped.execute(
        "fetch_web_page",
        {"url": "https://grants.openai.com/"},
    )
    assert not grants.is_error
    assert "https://grants.openai.com/" in fake.backend_calls

    # Verify streak reset semantics on a second exact hostname: failure,
    # success, then two new failures are needed before the next call blocks.
    first = await scoped.execute(
        "fetch_web_page",
        {"url": "https://reset.example/fail-1"},
    )
    assert first.error_type == "WEB_FETCH_HTTP_403"

    success = await scoped.execute(
        "fetch_web_page",
        {"url": "https://reset.example/ok"},
    )
    assert not success.is_error
    assert guard.failure_count("reset.example", "WEB_FETCH_HTTP_403") == 0

    second = await scoped.execute(
        "fetch_web_page",
        {"url": "https://reset.example/fail-2"},
    )
    third = await scoped.execute(
        "fetch_web_page",
        {"url": "https://reset.example/fail-3"},
    )
    blocked = await scoped.execute(
        "fetch_web_page",
        {"url": "https://reset.example/fail-4"},
    )
    assert second.error_type == "WEB_FETCH_HTTP_403"
    assert third.error_type == "WEB_FETCH_HTTP_403"
    assert blocked.error_type == "WEB_FETCH_REPEAT_BLOCKED"
    assert "https://reset.example/fail-4" not in fake.backend_calls

    print("M7-B.3 P1.1 SAME-HOST SERIALIZATION SMOKE PASSED")
    print("openai backend calls:", [u for u in fake.backend_calls if "openai.com" in u])
    print("guard block:", same_host[-1].error_type)
    print("reset streak after success: OK")


if __name__ == "__main__":
    asyncio.run(main())
