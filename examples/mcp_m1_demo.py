from __future__ import annotations

import asyncio

from dataclasses import dataclass
from enum import Enum, auto
from typing import Any, Awaitable, Callable


# ============================================================
# Data Contracts
# ============================================================


@dataclass(frozen=True)
class MCPRequest:
    request_id: int
    method: str
    params: dict[str, Any]


@dataclass(frozen=True)
class MCPResponse:
    request_id: int
    result: Any | None = None
    error: str | None = None


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    input_schema: dict[str, Any]


ToolHandler = Callable[
    [dict[str, Any]],
    Awaitable[Any],
]


class ClientState(Enum):
    DISCONNECTED = auto()
    CONNECTED = auto()
    INITIALIZING = auto()
    READY = auto()
    CLOSED = auto()


# ============================================================
# Mini MCP Server
# ============================================================


class MiniMCPServer:

    def __init__(
        self,
        *,
        protocol_version: str = "1",
    ) -> None:

        self.protocol_version = protocol_version

        self._initialized = False

        self._definitions: dict[
            str,
            ToolDefinition,
        ] = {}

        self._handlers: dict[
            str,
            ToolHandler,
        ] = {}

    def register_tool(
        self,
        *,
        definition: ToolDefinition,
        handler: ToolHandler,
    ) -> None:

        if definition.name in self._definitions:
            raise ValueError(
                f"duplicate tool: "
                f"{definition.name}"
            )

        self._definitions[
            definition.name
        ] = definition

        self._handlers[
            definition.name
        ] = handler

    async def handle(
        self,
        request: MCPRequest,
    ) -> MCPResponse:

        # ----------------------------------------------------
        # initialize
        # ----------------------------------------------------

        if request.method == "initialize":

            client_version = (
                request.params.get(
                    "protocol_version"
                )
            )

            if (
                client_version
                != self.protocol_version
            ):
                return MCPResponse(
                    request_id=request.request_id,
                    error=(
                        "protocol version mismatch"
                    ),
                )

            self._initialized = True

            return MCPResponse(
                request_id=request.request_id,
                result={
                    "protocol_version": (
                        self.protocol_version
                    ),
                    "server_name": (
                        "mini-mcp-server"
                    ),
                    "capabilities": {
                        "tools": True,
                    },
                },
            )

        # ----------------------------------------------------
        # protocol state guard
        # ----------------------------------------------------

        if not self._initialized:
            return MCPResponse(
                request_id=request.request_id,
                error=(
                    "server is not initialized"
                ),
            )

        # ----------------------------------------------------
        # tools/list
        # ----------------------------------------------------

        if request.method == "tools/list":

            tools = [
                {
                    "name": definition.name,
                    "description": (
                        definition.description
                    ),
                    "input_schema": (
                        definition.input_schema
                    ),
                }
                for definition
                in self._definitions.values()
            ]

            return MCPResponse(
                request_id=request.request_id,
                result={
                    "tools": tools,
                },
            )

        # ----------------------------------------------------
        # tools/call
        # ----------------------------------------------------

        if request.method == "tools/call":

            name = request.params.get(
                "name"
            )

            arguments = request.params.get(
                "arguments",
                {},
            )

            if not isinstance(name, str):
                return MCPResponse(
                    request_id=request.request_id,
                    error=(
                        "tool name must be string"
                    ),
                )

            if not isinstance(
                arguments,
                dict,
            ):
                return MCPResponse(
                    request_id=request.request_id,
                    error=(
                        "tool arguments "
                        "must be object"
                    ),
                )

            handler = self._handlers.get(
                name
            )

            if handler is None:
                return MCPResponse(
                    request_id=request.request_id,
                    error=(
                        f"unknown tool: {name}"
                    ),
                )

            try:
                content = await handler(
                    arguments
                )

            except Exception as exc:
                return MCPResponse(
                    request_id=request.request_id,
                    error=(
                        "tool execution failed: "
                        f"{type(exc).__name__}: "
                        f"{exc}"
                    ),
                )

            return MCPResponse(
                request_id=request.request_id,
                result={
                    "content": content,
                },
            )

        # ----------------------------------------------------
        # unknown method
        # ----------------------------------------------------

        return MCPResponse(
            request_id=request.request_id,
            error=(
                f"unknown method: "
                f"{request.method}"
            ),
        )


# ============================================================
# Mini MCP Client
# ============================================================


class MiniMCPClient:

    def __init__(
        self,
        *,
        protocol_version: str = "1",
    ) -> None:

        self.protocol_version = (
            protocol_version
        )

        self.state = (
            ClientState.DISCONNECTED
        )

        self._server: (
            MiniMCPServer | None
        ) = None

        self._next_request_id = 1

    async def connect(
        self,
        server: MiniMCPServer,
    ) -> None:

        if self.state is not (
            ClientState.DISCONNECTED
        ):
            raise RuntimeError(
                "client is already connected"
            )

        self._server = server

        self.state = (
            ClientState.CONNECTED
        )

    async def _send(
        self,
        *,
        method: str,
        params: dict[str, Any] | None = None,
    ) -> Any:

        if self._server is None:
            raise RuntimeError(
                "client is not connected"
            )

        request = MCPRequest(
            request_id=(
                self._next_request_id
            ),
            method=method,
            params=params or {},
        )

        self._next_request_id += 1

        response = await self._server.handle(
            request
        )

        if (
            response.request_id
            != request.request_id
        ):
            raise RuntimeError(
                "response id mismatch"
            )

        if response.error is not None:
            raise RuntimeError(
                response.error
            )

        return response.result

    async def initialize(
        self,
    ) -> None:

        if self.state is not (
            ClientState.CONNECTED
        ):
            raise RuntimeError(
                "client must be connected "
                "before initialize"
            )

        self.state = (
            ClientState.INITIALIZING
        )

        try:
            result = await self._send(
                method="initialize",
                params={
                    "protocol_version": (
                        self.protocol_version
                    ),
                    "client_name": (
                        "mini-mcp-client"
                    ),
                    "capabilities": {},
                },
            )

            if (
                result["protocol_version"]
                != self.protocol_version
            ):
                raise RuntimeError(
                    "invalid protocol version"
                )

            self.state = (
                ClientState.READY
            )

        except Exception:

            self.state = (
                ClientState.CONNECTED
            )

            raise

    def _ensure_ready(
        self,
    ) -> None:

        if self.state is not (
            ClientState.READY
        ):
            raise RuntimeError(
                "MCP client is not ready"
            )

    async def list_tools(
        self,
    ) -> tuple[
        ToolDefinition,
        ...
    ]:

        self._ensure_ready()

        result = await self._send(
            method="tools/list"
        )

        return tuple(
            ToolDefinition(
                name=item["name"],
                description=(
                    item["description"]
                ),
                input_schema=(
                    item["input_schema"]
                ),
            )
            for item in result["tools"]
        )

    async def call_tool(
        self,
        *,
        name: str,
        arguments: dict[str, Any],
    ) -> Any:

        self._ensure_ready()

        result = await self._send(
            method="tools/call",
            params={
                "name": name,
                "arguments": arguments,
            },
        )

        return result["content"]

    async def close(
        self,
    ) -> None:

        self._server = None

        self.state = (
            ClientState.CLOSED
        )


# ============================================================
# Example Remote Tool
# ============================================================


async def multiply(
    arguments: dict[str, Any],
) -> int:

    a = arguments.get("a")
    b = arguments.get("b")

    if not isinstance(a, int):
        raise ValueError(
            "a must be integer"
        )

    if not isinstance(b, int):
        raise ValueError(
            "b must be integer"
        )

    return a * b


# ============================================================
# Demo
# ============================================================


async def main() -> None:

    server = MiniMCPServer(
        protocol_version="1"
    )

    server.register_tool(
        definition=ToolDefinition(
            name="multiply",
            description=(
                "计算两个整数的乘积"
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "a": {
                        "type": "integer",
                    },
                    "b": {
                        "type": "integer",
                    },
                },
                "required": [
                    "a",
                    "b",
                ],
            },
        ),
        handler=multiply,
    )

    client = MiniMCPClient(
        protocol_version="1"
    )

    print(
        "[1] connect"
    )

    await client.connect(
        server
    )

    print(
        "    state:",
        client.state.name,
    )

    print(
        "\n[2] initialize"
    )

    # await client.initialize()

    print(
        "    state:",
        client.state.name,
    )

    print(
        "\n[3] tools/list"
    )

    tools = await client.list_tools()

    for tool in tools:
        print(
            f"    {tool.name}"
        )

        print(
            f"    {tool.description}"
        )

        print(
            f"    {tool.input_schema}"
        )

    print(
        "\n[4] tools/call"
    )

    result = await client.call_tool(
        name="multiply",
        arguments={
            "a": 6,
            "b": 7,
        },
    )

    print(
        "    6 × 7 =",
        result,
    )

    await client.close()


if __name__ == "__main__":

    asyncio.run(
        main()
    )
