from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.mcp.contracts import (
    MCPCallResult,
    MCPPromptResult,
    MCPRemotePrompt,
    MCPRemoteResource,
    MCPRemoteTool,
    MCPResourceContent,
    MCPServerCapabilities,
)


@dataclass(frozen=True)
class RecordedMCPCall:
    name: str
    arguments: dict[str, Any]


class FakeMCPClient:
    def __init__(
        self,
        *,
        server_name: str,
        tools: tuple[MCPRemoteTool, ...] = (),
        responses: dict[str, MCPCallResult] | None = None,
        resources: tuple[MCPRemoteResource, ...] = (),
        resource_contents: dict[
            str,
            tuple[MCPResourceContent, ...],
        ] | None = None,
        prompts: tuple[MCPRemotePrompt, ...] = (),
        prompt_results: dict[str, MCPPromptResult] | None = None,
        capabilities: MCPServerCapabilities | None = None,
    ) -> None:
        self._server_name = server_name
        self._tools = tools
        self._responses = responses or {}
        self._resources = resources
        self._resource_contents = resource_contents or {}
        self._prompts = prompts
        self._prompt_results = prompt_results or {}

        self._capabilities = capabilities or MCPServerCapabilities(
            tools=bool(tools),
            resources=bool(resources),
            prompts=bool(prompts),
        )

        self.calls: list[RecordedMCPCall] = []
        self.closed = False

    @property
    def server_name(self) -> str:
        return self._server_name

    @property
    def capabilities(self) -> MCPServerCapabilities:
        return self._capabilities

    async def list_tools(self) -> tuple[MCPRemoteTool, ...]:
        return self._tools

    async def call_tool(
        self,
        *,
        name: str,
        arguments: dict[str, Any],
    ) -> MCPCallResult:
        self.calls.append(
            RecordedMCPCall(
                name=name,
                arguments=dict(arguments),
            )
        )

        result = self._responses.get(name)

        if result is None:
            return MCPCallResult(
                content=f"unknown remote tool: {name}",
                is_error=True,
            )

        return result

    async def list_resources(self) -> tuple[MCPRemoteResource, ...]:
        return self._resources

    async def read_resource(
        self,
        *,
        uri: str,
    ) -> tuple[MCPResourceContent, ...]:
        if uri not in self._resource_contents:
            raise KeyError(f"unknown resource: {uri}")

        return self._resource_contents[uri]

    async def list_prompts(self) -> tuple[MCPRemotePrompt, ...]:
        return self._prompts

    async def get_prompt(
        self,
        *,
        name: str,
        arguments: dict[str, str],
    ) -> MCPPromptResult:
        del arguments

        if name not in self._prompt_results:
            raise KeyError(f"unknown prompt: {name}")

        return self._prompt_results[name]

    async def close(self) -> None:
        self.closed = True