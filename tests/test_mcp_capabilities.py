from __future__ import annotations

import sys
from pathlib import Path

import pytest

from app.mcp.config import StdioMCPServerConfig
from app.mcp.manager import MCPManager
from app.mcp.sdk_client import SDKMCPClient
from app.mcp.security import (
    MCPSecurityPolicy,
    MCPToolPermission,
    MCPToolRisk,
)
from app.tools.registry import ToolRegistry


PROJECT_ROOT = Path(__file__).resolve().parents[1]

SERVER_FILE = (
    PROJECT_ROOT
    / "examples"
    / "mcp_demo_server.py"
)


@pytest.mark.asyncio
async def test_real_mcp_tools_resources_and_prompts():
    client = await SDKMCPClient.connect_stdio(
        StdioMCPServerConfig(
            name="demo",
            command=sys.executable,
            args=(str(SERVER_FILE),),
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
        resource_servers=frozenset({"demo"}),
        prompt_servers=frozenset({"demo"}),
    )

    manager = MCPManager(
        registry=registry,
        clients=(client,),
        security_policy=policy,
    )

    try:
        await manager.start()

        assert (
            "mcp__demo__lookup_demo_record"
            in registry.names()
        )

        assert any(
            entry.resource.uri == "demo://guide"
            for entry in manager.resource_entries
        )

        resource_contents = await manager.read_resource(
            server_name="demo",
            uri="demo://guide",
        )

        assert any(
            content.text is not None
            and "MCP Resource Demo" in content.text
            for content in resource_contents
        )

        assert any(
            entry.local_name
            == "mcp__demo__prompt__explain_demo_record"
            for entry in manager.prompt_entries
        )

        prompt_result = await manager.get_prompt(
            local_name=(
                "mcp__demo__prompt__"
                "explain_demo_record"
            ),
            arguments={
                "record_id": "A-100",
            },
        )

        assert prompt_result.messages

        assert (
            "A-100"
            in prompt_result.messages[0].text
        )

    finally:
        await manager.close()