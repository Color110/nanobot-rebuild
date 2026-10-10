from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class MCPToolRisk(StrEnum):
    READ_ONLY = "READ_ONLY"
    WRITE = "WRITE"
    HIGH_RISK = "HIGH_RISK"


@dataclass(frozen=True)
class MCPToolPermission:
    server_name: str
    tool_name: str
    risk: MCPToolRisk = MCPToolRisk.READ_ONLY
    enabled: bool = True
    require_confirmation: bool = False


@dataclass(frozen=True)
class MCPSecurityPolicy:
    allowed_servers: frozenset[str]
    tool_permissions: tuple[MCPToolPermission, ...]
    resource_servers: frozenset[str] = frozenset()
    prompt_servers: frozenset[str] = frozenset()
    max_tool_result_chars: int = 20_000

    def __post_init__(self) -> None:
        if self.max_tool_result_chars <= 0:
            raise ValueError("max_tool_result_chars 必须大于 0")

    def ensure_server_allowed(self, server_name: str) -> None:
        if server_name not in self.allowed_servers:
            raise PermissionError(
                f"MCP Server 未授权: {server_name}"
            )

    def get_tool_permission(
        self,
        *,
        server_name: str,
        tool_name: str,
    ) -> MCPToolPermission | None:
        for permission in self.tool_permissions:
            if (
                permission.server_name == server_name
                and permission.tool_name == tool_name
            ):
                return permission

        return None

    def resources_allowed(self, server_name: str) -> bool:
        return server_name in self.resource_servers

    def prompts_allowed(self, server_name: str) -> bool:
        return server_name in self.prompt_servers