import pytest

from app.mcp.contracts import MCPCallResult, MCPRemoteTool
from app.mcp.manager import MCPManager
from app.mcp.security import (
    MCPSecurityPolicy,
    MCPToolPermission,
    MCPToolRisk,
)
from app.tools.registry import ToolRegistry
from tests.fakes.mcp import FakeMCPClient


@pytest.mark.asyncio
async def test_unlisted_tool_is_not_registered():
    client = FakeMCPClient(
        server_name="demo",
        tools=(
            MCPRemoteTool(
                name="read",
                description="读取数据",
                input_schema={"type": "object"},
            ),
            MCPRemoteTool(
                name="delete",
                description="删除数据",
                input_schema={"type": "object"},
            ),
        ),
        responses={},
    )

    policy = MCPSecurityPolicy(
        allowed_servers=frozenset({"demo"}),
        tool_permissions=(
            MCPToolPermission(
                server_name="demo",
                tool_name="read",
            ),
        ),
    )

    registry = ToolRegistry()

    manager = MCPManager(
        registry=registry,
        clients=(client,),
        security_policy=policy,
    )

    await manager.start()

    assert "mcp__demo__read" in registry.names()
    assert "mcp__demo__delete" not in registry.names()

@pytest.mark.asyncio
async def test_high_risk_tool_requires_confirmation():
    client = FakeMCPClient(
        server_name="demo",
        tools=(
            MCPRemoteTool(
                name="delete",
                description="删除数据",
                input_schema={"type": "object"},
            ),
        ),
        responses={
            "delete": MCPCallResult(
                content="deleted",
                is_error=False,
            ),
        },
    )

    policy = MCPSecurityPolicy(
        allowed_servers=frozenset({"demo"}),
        tool_permissions=(
            MCPToolPermission(
                server_name="demo",
                tool_name="delete",
                risk=MCPToolRisk.HIGH_RISK,
                require_confirmation=True,
            ),
        ),
    )

    registry = ToolRegistry()

    manager = MCPManager(
        registry=registry,
        clients=(client,),
        security_policy=policy,
    )

    await manager.start()

    result = await registry.execute(
        name="mcp__demo__delete",
        arguments={},
    )

    assert result.is_error is True
    assert result.error_type == "MCP_CONFIRMATION_REQUIRED"
    assert client.calls == []

@pytest.mark.asyncio
async def test_oversized_mcp_result_is_blocked():
    client = FakeMCPClient(
        server_name="demo",
        tools=(
            MCPRemoteTool(
                name="read",
                description="读取数据",
                input_schema={"type": "object"},
            ),
        ),
        responses={
            "read": MCPCallResult(
                content="x" * 100,
                is_error=False,
            ),
        },
    )

    policy = MCPSecurityPolicy(
        allowed_servers=frozenset({"demo"}),
        tool_permissions=(
            MCPToolPermission(
                server_name="demo",
                tool_name="read",
            ),
        ),
        max_tool_result_chars=32,
    )

    registry = ToolRegistry()

    manager = MCPManager(
        registry=registry,
        clients=(client,),
        security_policy=policy,
    )

    await manager.start()

    result = await registry.execute(
        name="mcp__demo__read",
        arguments={},
    )

    assert result.is_error is True
    assert result.error_type == "MCP_RESULT_TOO_LARGE"
