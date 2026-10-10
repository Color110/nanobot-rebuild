from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class MCPServerCapabilities:
    tools: bool = False
    resources: bool = False
    prompts: bool = False


@dataclass(frozen=True)
class MCPRemoteTool:
    name: str
    description: str
    input_schema: dict[str, Any]


@dataclass(frozen=True)
class MCPCallResult:
    content: str
    is_error: bool = False


@dataclass(frozen=True)
class MCPRemoteResource:
    uri: str
    name: str
    description: str = ""
    mime_type: str | None = None


@dataclass(frozen=True)
class MCPResourceContent:
    uri: str
    mime_type: str | None = None
    text: str | None = None
    blob: str | None = None


@dataclass(frozen=True)
class MCPPromptArgument:
    name: str
    description: str = ""
    required: bool = False


@dataclass(frozen=True)
class MCPRemotePrompt:
    name: str
    description: str = ""
    arguments: tuple[MCPPromptArgument, ...] = ()


@dataclass(frozen=True)
class MCPPromptMessage:
    role: str
    text: str


@dataclass(frozen=True)
class MCPPromptResult:
    description: str | None
    messages: tuple[MCPPromptMessage, ...]


class MCPClient(Protocol):
    @property
    def server_name(self) -> str:
        ...

    @property
    def capabilities(self) -> MCPServerCapabilities:
        ...

    async def list_tools(self) -> tuple[MCPRemoteTool, ...]:
        ...

    async def call_tool(
        self,
        *,
        name: str,
        arguments: dict[str, Any],
    ) -> MCPCallResult:
        ...

    async def list_resources(self) -> tuple[MCPRemoteResource, ...]:
        ...

    async def read_resource(
        self,
        *,
        uri: str,
    ) -> tuple[MCPResourceContent, ...]:
        ...

    async def list_prompts(self) -> tuple[MCPRemotePrompt, ...]:
        ...

    async def get_prompt(
        self,
        *,
        name: str,
        arguments: dict[str, str],
    ) -> MCPPromptResult:
        ...

    async def close(self) -> None:
        ...