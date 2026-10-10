from __future__ import annotations

import asyncio

from pydantic import BaseModel, ConfigDict, Field

from app.orchestration.capabilities import ScopedToolRegistry
from app.tools.base import PydanticTool, ToolExecutionError
from app.tools.registry import ToolRegistry
from app.web.failure_guard import WebFetchFailureGuard


class Args(BaseModel):
    model_config = ConfigDict(extra="forbid")
    url: str = Field(min_length=1)


class FakeFetchTool(PydanticTool):
    def __init__(self) -> None:
        self.calls: list[str] = []

    @property
    def name(self) -> str:
        return "fetch_web_page"

    @property
    def description(self) -> str:
        return "fake fetch"

    @property
    def argument_model(self) -> type[BaseModel]:
        return Args

    async def execute(self, **kwargs):
        url = kwargs["url"]
        self.calls.append(url)
        if "openai.com" in url and "grants.openai.com" not in url:
            raise ToolExecutionError(
                "HTTP 403 Forbidden",
                error_type="WEB_FETCH_HTTP_403",
            )
        return "OK"


async def main() -> None:
    parent = ToolRegistry()
    fake = FakeFetchTool()
    parent.register(fake)

    scoped = ScopedToolRegistry(
        parent=parent,
        allowed_tools=("fetch_web_page",),
        guards=(WebFetchFailureGuard(),),
    )

    r1 = await scoped.execute("fetch_web_page", {"url": "https://openai.com/a"})
    r2 = await scoped.execute("fetch_web_page", {"url": "https://openai.com/b"})
    r3 = await scoped.execute("fetch_web_page", {"url": "https://openai.com/c"})
    r4 = await scoped.execute("fetch_web_page", {"url": "https://grants.openai.com/"})

    assert r1.error_type == "WEB_FETCH_HTTP_403"
    assert r2.error_type == "WEB_FETCH_HTTP_403"
    assert r3.error_type == "WEB_FETCH_REPEAT_BLOCKED"
    assert r4.is_error is False
    assert len(fake.calls) == 3, fake.calls
    assert "https://openai.com/c" not in fake.calls
    assert "https://grants.openai.com/" in fake.calls

    print("M7-B.3 WEB FETCH GUARD SMOKE PASSED")
    print("backend_calls:", fake.calls)
    print("blocked_error:", r3.error_type)


if __name__ == "__main__":
    asyncio.run(main())
