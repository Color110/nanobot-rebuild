import pytest

from app.mcp.contracts import MCPCallResult, MCPRemoteTool
from app.mcp.manager import MCPManager
from app.tools.registry import ToolRegistry
from tests.fakes.mcp import FakeMCPClient
from app.mcp.security import (
    MCPSecurityPolicy,
    MCPToolPermission,
    MCPToolRisk,
)


def build_filesystem_client() -> FakeMCPClient:
    return FakeMCPClient(
        server_name="filesystem",
        tools=(
            MCPRemoteTool(
                name="search",
                description="搜索工作目录中的文件",
                input_schema={
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                    "required": ["query"],
                    "additionalProperties": False,
                },
            ),
        ),
        responses={
            "search": MCPCallResult(content="filesystem-result", is_error=False),
        },
    )


def build_github_client() -> FakeMCPClient:
    return FakeMCPClient(
        server_name="github",
        tools=(
            MCPRemoteTool(
                name="search",
                description="搜索 GitHub 内容",
                input_schema={
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                    "required": ["query"],
                    "additionalProperties": False,
                },
            ),
        ),
        responses={
            "search": MCPCallResult(content="github-result", is_error=False),
        },
    )


@pytest.mark.asyncio
async def test_manager_discovers_and_registers_tools():
    registry = ToolRegistry()
    filesystem = build_filesystem_client()
    policy = MCPSecurityPolicy(
        allowed_servers=frozenset({"filesystem"}),
        tool_permissions=(
            MCPToolPermission(
                server_name="filesystem",
                tool_name="search",
                risk=MCPToolRisk.READ_ONLY,
            ),
        ),
    )
    manager = MCPManager(
        registry=registry,
        clients=(filesystem,),
        security_policy=policy,
    )
    registered = await manager.start()

    assert registered == ("mcp__filesystem__search",)
    assert "mcp__filesystem__search" in registry.names()
    assert manager.started is True


@pytest.mark.asyncio
async def test_same_remote_name_from_two_servers_is_namespaced():
    registry = ToolRegistry()
    filesystem = build_filesystem_client()
    github = build_github_client()
    policy = MCPSecurityPolicy(
        allowed_servers=frozenset({"filesystem", "github"}),
        tool_permissions=(
            MCPToolPermission(
                server_name="filesystem",
                tool_name="search",
                risk=MCPToolRisk.READ_ONLY,
            ),
            MCPToolPermission(
                server_name="github",
                tool_name="search",
                risk=MCPToolRisk.READ_ONLY,
            ),
        ),
    )
    manager = MCPManager(
        registry=registry,
        clients=(filesystem, github),
        security_policy=policy,
    )


    await manager.start()

    assert set(registry.names()) == {
        "mcp__filesystem__search",
        "mcp__github__search",
    }

    filesystem_result = await registry.execute(
        name="mcp__filesystem__search",
        arguments={"query": "README"},
    )

    github_result = await registry.execute(
        name="mcp__github__search",
        arguments={"query": "README"},
    )


    assert filesystem_result.content == "filesystem-result"
    assert github_result.content == "github-result"
    assert filesystem.calls[0].name == "search"
    assert github.calls[0].name == "search"


@pytest.mark.asyncio
async def test_start_failure_does_not_partially_modify_registry():
    registry = ToolRegistry()

    first = FakeMCPClient(
        server_name="duplicate",
        tools=(
            MCPRemoteTool(
                name="tool_a",
                description="Tool A",
                input_schema={"type": "object"},
            ),
        ),
        responses={},
    )

    second = FakeMCPClient(
        server_name="duplicate",
        tools=(
            MCPRemoteTool(
                name="tool_b",
                description="Tool B",
                input_schema={"type": "object"},
            ),
        ),
        responses={},
    )
    policy = MCPSecurityPolicy(
        allowed_servers=frozenset({"duplicate"}),
        tool_permissions=(),
    )
    manager = MCPManager(
        registry=registry,
        clients=(first, second),
        security_policy=policy,
    )
    with pytest.raises(ValueError, match="Server 名称重复"):
        await manager.start()

    assert registry.names() == []
    assert manager.started is False