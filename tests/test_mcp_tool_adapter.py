import pytest

from app.mcp.contracts import (
    MCPCallResult,
    MCPRemoteTool,
)
from app.mcp.tool_adapter import (
    MCPToolAdapter,
)
from app.tools.registry import (
    ToolRegistry,
)
from tests.fakes.mcp import (
    FakeMCPClient,
)
from app.mcp.security import (
    MCPToolPermission,
    MCPToolRisk,
)

def build_fake_client(
) -> FakeMCPClient:

    return FakeMCPClient(
        server_name="filesystem",
        tools=(
            MCPRemoteTool(
                name="read_file",
                description=(
                    "读取工作目录中的文本文件"
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                        },
                    },
                    "required": [
                        "path",
                    ],
                    "additionalProperties": (
                        False
                    ),
                },
            ),
        ),
        responses={
            "read_file": (
                MCPCallResult(
                    content=(
                        "README CONTENT"
                    ),
                    is_error=False,
                )
            ),
        },
    )


@pytest.mark.asyncio
async def test_mcp_tool_is_visible_to_registry():

    client = build_fake_client()

    remote_tools = (
        await client.list_tools()
    )

    adapter = MCPToolAdapter(
        client=client,
        remote_tool=remote_tools[0],
        permission=MCPToolPermission(
            server_name="filesystem",
            tool_name="read_file",
            risk=MCPToolRisk.READ_ONLY,
        ),
        max_result_chars=20_000,
    )

    registry = ToolRegistry()

    registry.register(
        adapter
    )

    assert (
        "mcp__filesystem__read_file"
        in registry.names()
    )

    definitions = (
        registry.get_definitions()
    )

    assert (
        definitions[0]["function"][
            "name"
        ]
        == "mcp__filesystem__read_file"
    )

    assert (
        definitions[0]["function"][
            "parameters"
        ]["required"]
        == ["path"]
    )


@pytest.mark.asyncio
async def test_registry_routes_to_remote_mcp_tool():

    client = build_fake_client()

    remote_tools = (
        await client.list_tools()
    )

    adapter = MCPToolAdapter(
        client=client,
        remote_tool=remote_tools[0],
        permission=MCPToolPermission(
            server_name="filesystem",
            tool_name="read_file",
            risk=MCPToolRisk.READ_ONLY,
        ),
        max_result_chars=20_000,
    )

    registry = ToolRegistry()

    registry.register(
        adapter
    )

    result = (
        await registry.execute(
            name=(
                "mcp__filesystem__"
                "read_file"
            ),
            arguments={
                "path": "README.md",
            },
        )
    )

    assert result.is_error is False

    assert (
        result.content
        == "README CONTENT"
    )

    assert len(
        client.calls
    ) == 1

    assert (
        client.calls[0].name
        == "read_file"
    )

    assert (
        client.calls[0].arguments
        == {
            "path": "README.md",
        }
    )


@pytest.mark.asyncio
async def test_invalid_arguments_do_not_reach_mcp_server():

    client = build_fake_client()

    remote_tools = (
        await client.list_tools()
    )

    adapter = MCPToolAdapter(
        client=client,
        remote_tool=remote_tools[0],
        permission=MCPToolPermission(
            server_name="filesystem",
            tool_name="read_file",
            risk=MCPToolRisk.READ_ONLY,
        ),
        max_result_chars=20_000,
    )
    registry = ToolRegistry()

    registry.register(
        adapter
    )

    result = (
        await registry.execute(
            name=(
                "mcp__filesystem__"
                "read_file"
            ),
            arguments={
                "path": 123,
            },
        )
    )

    assert result.is_error is True

    assert (
        result.error_type
        == "VALIDATION_ERROR"
    )

    assert client.calls == []