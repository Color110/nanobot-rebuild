import asyncio
import time
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.agent import run_agent_turn
from app.conversation import add_message, create_conversation
from app.providers import FakeProvider, ProviderResponse, ToolCallRequest
from app.tools.base import BaseTool
from app.tools.registry import ToolRegistry
from app.providers.base import (
    LLMProvider,
    ProviderError,
    ProviderResponse,
    ToolCallRequest,
)

class SlowArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str
    delay: float


class SlowTool(BaseTool):
    @property
    def name(self) -> str:
        return "slow"

    @property
    def description(self) -> str:
        return "测试并发执行。"

    @property
    def argument_model(self) -> type[BaseModel]:
        return SlowArguments

    async def execute(self, **kwargs: Any) -> str:
        await asyncio.sleep(kwargs["delay"])
        return kwargs["label"]


async def test_multiple_tools_run_concurrently():
    provider = FakeProvider(
        responses=[
            ProviderResponse(
                content="",
                tool_calls=[
                    ToolCallRequest(
                        id="call_a",
                        name="slow",
                        arguments={
                            "label": "A",
                            "delay": 0.2,
                        },
                    ),
                    ToolCallRequest(
                        id="call_b",
                        name="slow",
                        arguments={
                            "label": "B",
                            "delay": 0.2,
                        },
                    ),
                ],
            ),
            ProviderResponse(
                content="done",
                tool_calls=[],
            ),
        ]
    )

    registry = ToolRegistry()
    registry.register(SlowTool())

    messages = create_conversation()
    add_message(messages, "user", "执行两个慢任务")

    start = time.perf_counter()

    result = await run_agent_turn(
        messages=messages,
        provider=provider,
        tool_registry=registry,
        concurrent_tools=True,
    )

    elapsed = time.perf_counter() - start

    assert result.final_content == "done"
    assert len(result.tools_used) == 2

    # 两个 0.2 秒任务并发执行，
    # 正常应明显小于串行的约 0.4 秒。
    assert elapsed < 0.35