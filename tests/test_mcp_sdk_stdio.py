from __future__ import annotations

import sys

from pathlib import Path

import pytest

from app.mcp.config import (
    StdioMCPServerConfig,
)
from app.mcp.manager import (
    MCPManager,
)
from app.mcp.sdk_client import (
    SDKMCPClient,
)
from app.tools.registry import (
    ToolRegistry,
)
from app.mcp.security import (
    MCPSecurityPolicy,
    MCPToolPermission,
    MCPToolRisk,
)

PROJECT_ROOT = (
    Path(__file__)
    .resolve()
    .parents[1]
)

SERVER_FILE = (
    PROJECT_ROOT
    / "examples"
    / "mcp_demo_server.py"
)


@pytest.mark.asyncio
async def test_real_stdio_mcp_roundtrip():

    config = (
        StdioMCPServerConfig(
            name="demo",
            command=sys.executable,
            args=(
                str(SERVER_FILE),
            ),
        )
    )

    client = (
        await SDKMCPClient
        .connect_stdio(
            config
        )
    )

    registry = ToolRegistry()

    policy = MCPSecurityPolicy(
        allowed_servers=frozenset({"demo"}),
        tool_permissions=(
            MCPToolPermission(
                server_name="demo",
                tool_name="lookup_demo_record",
                risk=MCPToolRisk.READ_ONLY,
            ),
        ),
    )

    manager = MCPManager(
        registry=registry,
        clients=(client,),
        security_policy=policy,
    )

    try:

        registered = (
            await manager.start()
        )

        assert (
            "mcp__demo__"
            "lookup_demo_record"
            in registered
        )

        assert (
            "mcp__demo__"
            "lookup_demo_record"
            in registry.names()
        )

        result = (
            await registry.execute(
                name=(
                    "mcp__demo__"
                    "lookup_demo_record"
                ),
                arguments={
                    "record_id": (
                        "A-100"
                    ),
                },
            )
        )

        assert (
            result.is_error
            is False
        )

        assert (
            "MCP-DEMO-OK"
            in result.content
        )

    finally:

        await manager.close()