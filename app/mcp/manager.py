from __future__ import annotations

import asyncio
from dataclasses import dataclass

from app.mcp.contracts import (
    MCPClient,
    MCPPromptResult,
    MCPRemotePrompt,
    MCPRemoteResource,
    MCPResourceContent,
)
from app.mcp.naming import make_mcp_prompt_name
from app.mcp.tool_adapter import MCPToolAdapter
from app.tools.base import BaseTool
from app.tools.registry import ToolRegistry
from app.mcp.security import MCPSecurityPolicy

@dataclass(frozen=True)
class MCPResourceEntry:
    server_name: str
    resource: MCPRemoteResource


@dataclass(frozen=True)
class MCPPromptEntry:
    server_name: str
    local_name: str
    prompt: MCPRemotePrompt


class MCPManager:
    def __init__(
        self,
        *,
        registry: ToolRegistry,
        clients: tuple[MCPClient, ...],
        security_policy: MCPSecurityPolicy,
    ) -> None:
        self._registry = registry
        self._clients = clients
        self._security_policy = security_policy

        self._clients_by_name: dict[str, MCPClient] = {}

        self._started = False

        self._registered_tool_names: tuple[str, ...] = ()
        self._resource_entries: tuple[MCPResourceEntry, ...] = ()
        self._prompt_entries: tuple[MCPPromptEntry, ...] = ()
    @property
    def started(self) -> bool:
        return self._started

    @property
    def registered_tool_names(self) -> tuple[str, ...]:
        return self._registered_tool_names

    @property
    def resource_entries(self) -> tuple[MCPResourceEntry, ...]:
        return self._resource_entries

    @property
    def prompt_entries(self) -> tuple[MCPPromptEntry, ...]:
        return self._prompt_entries

    async def start(self) -> tuple[str, ...]:
        if self._started:
            raise RuntimeError("MCPManager 已经启动")

        staged_tools: list[BaseTool] = []
        staged_resources: list[MCPResourceEntry] = []
        staged_prompts: list[MCPPromptEntry] = []
        staged_clients: dict[str, MCPClient] = {}

        seen_tool_names = set(self._registry.names())
        seen_resource_keys: set[tuple[str, str]] = set()
        seen_prompt_names: set[str] = set()

        for client in self._clients:
            
            server_name = client.server_name
            self._security_policy.ensure_server_allowed(server_name)
            if server_name in staged_clients:
                raise ValueError(f"MCP Server 名称重复: {server_name}")

            staged_clients[server_name] = client
            capabilities = client.capabilities

            if capabilities.tools:
                remote_tools = await client.list_tools()

                for remote_tool in remote_tools:
                    permission = self._security_policy.get_tool_permission(
                        server_name=server_name,
                        tool_name=remote_tool.name,
                    )

                    if permission is None or not permission.enabled:
                        continue

                    adapter = MCPToolAdapter(
                        client=client,
                        remote_tool=remote_tool,
                        permission=permission,
                        max_result_chars=self._security_policy.max_tool_result_chars,
                    )
                    if adapter.name in seen_tool_names:
                        raise ValueError(f"Tool 名称冲突: {adapter.name}")

                    seen_tool_names.add(adapter.name)
                    staged_tools.append(adapter)

            if (
                capabilities.resources
                and self._security_policy.resources_allowed(server_name)
            ):
                resources = await client.list_resources()

                for resource in resources:
                    key = (server_name, resource.uri)

                    if key in seen_resource_keys:
                        raise ValueError(
                            f"MCP Resource 重复: {server_name} {resource.uri}"
                        )

                    seen_resource_keys.add(key)
                    staged_resources.append(
                        MCPResourceEntry(
                            server_name=server_name,
                            resource=resource,
                        )
                    )
        
            if (
                capabilities.prompts
                and self._security_policy.prompts_allowed(server_name)
            ):
                prompts = await client.list_prompts()

                for prompt in prompts:
                    local_name = make_mcp_prompt_name(
                        server_name=server_name,
                        prompt_name=prompt.name,
                    )

                    if local_name in seen_prompt_names:
                        raise ValueError(f"MCP Prompt 名称冲突: {local_name}")

                    seen_prompt_names.add(local_name)
                    staged_prompts.append(
                        MCPPromptEntry(
                            server_name=server_name,
                            local_name=local_name,
                            prompt=prompt,
                        )
                    )

        for tool in staged_tools:
            self._registry.register(tool)

        self._clients_by_name = staged_clients
        self._registered_tool_names = tuple(
            tool.name for tool in staged_tools
        )
        self._resource_entries = tuple(staged_resources)
        self._prompt_entries = tuple(staged_prompts)
        self._started = True

        return self._registered_tool_names

    async def read_resource(
        self,
        *,
        server_name: str,
        uri: str,
    ) -> tuple[MCPResourceContent, ...]:
        self._ensure_started()

        known = any(
            entry.server_name == server_name and entry.resource.uri == uri
            for entry in self._resource_entries
        )

        if not known:
            raise KeyError(f"未知 MCP Resource: {server_name} {uri}")

        client = self._clients_by_name[server_name]
        return await client.read_resource(uri=uri)

    async def get_prompt(
        self,
        *,
        local_name: str,
        arguments: dict[str, str],
    ) -> MCPPromptResult:
        self._ensure_started()

        entry = next(
            (
                item
                for item in self._prompt_entries
                if item.local_name == local_name
            ),
            None,
        )

        if entry is None:
            raise KeyError(f"未知 MCP Prompt: {local_name}")

        client = self._clients_by_name[entry.server_name]

        return await client.get_prompt(
            name=entry.prompt.name,
            arguments=arguments,
        )

    def _ensure_started(self) -> None:
        if not self._started:
            raise RuntimeError("MCPManager 尚未启动")

    async def close(self) -> None:
        failures: list[Exception] = []

        for client in self._clients:
            try:
                await client.close()
            except Exception as exc:
                failures.append(exc)

        self._started = False

        if failures:
            message = "; ".join(
                f"{type(error).__name__}: {error}"
                for error in failures
            )
            raise RuntimeError(
                f"关闭 MCP Client 失败: {message}"
            )