import asyncio
from contextlib import AsyncExitStack

import pytest

from app.mcp.contracts import MCPServerCapabilities
from app.mcp.errors import MCPTimeoutError
from app.mcp.policy import MCPRequestPolicy
from app.mcp.sdk_client import SDKMCPClient
from app.mcp.state import MCPClientState


class SlowSession:
    async def call_tool(self, *, name, arguments):
        await asyncio.sleep(1.0)


@pytest.mark.asyncio
async def test_mcp_request_timeout():
    client = SDKMCPClient(
        server_name="slow",
        session=SlowSession(),
        exit_stack=AsyncExitStack(),
        capabilities=MCPServerCapabilities(tools=True),
        policy=MCPRequestPolicy(
            request_timeout_seconds=0.01,
            max_concurrency=1,
        ),
    )

    with pytest.raises(MCPTimeoutError):
        await client.call_tool(
            name="slow_tool",
            arguments={},
        )

    assert client.state == MCPClientState.READY


@pytest.mark.asyncio
async def test_cancellation_is_not_converted_to_transport_error():
    client = SDKMCPClient(
        server_name="slow",
        session=SlowSession(),
        exit_stack=AsyncExitStack(),
        capabilities=MCPServerCapabilities(tools=True),
        policy=MCPRequestPolicy(
            request_timeout_seconds=10.0,
            max_concurrency=1,
        ),
    )

    task = asyncio.create_task(
        client.call_tool(
            name="slow_tool",
            arguments={},
        )
    )

    await asyncio.sleep(0.01)
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task

    assert client.state == MCPClientState.READY

class ConcurrentSession:
    def __init__(self):
        self.active = 0
        self.max_active = 0

    async def call_tool(self, *, name, arguments):
        self.active += 1
        self.max_active = max(self.max_active, self.active)

        try:
            await asyncio.sleep(0.03)

            return type(
                "Result",
                (),
                {
                    "content": [],
                    "isError": False,
                    "structuredContent": {},
                },
            )()

        finally:
            self.active -= 1


@pytest.mark.asyncio
async def test_mcp_concurrency_limit():
    session = ConcurrentSession()

    client = SDKMCPClient(
        server_name="limited",
        session=session,
        exit_stack=AsyncExitStack(),
        capabilities=MCPServerCapabilities(tools=True),
        policy=MCPRequestPolicy(
            request_timeout_seconds=1.0,
            max_concurrency=2,
        ),
    )

    await asyncio.gather(
        *(
            client.call_tool(
                name="demo",
                arguments={"n": index},
            )
            for index in range(6)
        )
    )

    assert session.max_active == 2