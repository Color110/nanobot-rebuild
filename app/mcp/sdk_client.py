from __future__ import annotations

import json
import os
from contextlib import AsyncExitStack
from copy import deepcopy
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from app.mcp.config import StdioMCPServerConfig
from app.mcp.contracts import (
    MCPCallResult,
    MCPPromptArgument,
    MCPPromptMessage,
    MCPPromptResult,
    MCPRemotePrompt,
    MCPRemoteResource,
    MCPRemoteTool,
    MCPResourceContent,
    MCPServerCapabilities,
)
import asyncio

from collections.abc import Awaitable, Callable
from typing import TypeVar
from app.mcp.errors import (
    MCPStateError,
    MCPTimeoutError,
    MCPTransportError,
)
from app.mcp.policy import MCPRequestPolicy
from app.mcp.state import MCPClientState
T = TypeVar("T")

class SDKMCPClient:
    def __init__(
        self,
        *,
        server_name: str,
        session: ClientSession,
        exit_stack: AsyncExitStack,
        capabilities: MCPServerCapabilities,
        policy: MCPRequestPolicy,
    ) -> None:
        self._server_name = server_name
        self._session = session
        self._exit_stack = exit_stack
        self._capabilities = capabilities
        self._policy = policy

        self._state = MCPClientState.READY
        self._semaphore = asyncio.Semaphore(policy.max_concurrency)

    @property
    def server_name(self) -> str:
        return self._server_name

    @property
    def capabilities(self) -> MCPServerCapabilities:
        return self._capabilities
    @property
    def state(self) -> MCPClientState:
        return self._state
    @classmethod
    async def connect_stdio(
        cls,
        config: StdioMCPServerConfig,
        policy: MCPRequestPolicy | None = None,
    ) -> "SDKMCPClient":
        policy = policy or MCPRequestPolicy()
        exit_stack = AsyncExitStack()

        try:
            env: dict[str, str] | None = None
            if config.env is not None:
                env = dict(os.environ)
                env.update(dict(config.env))

            server_params = StdioServerParameters(
                command=config.command,
                args=list(config.args),
                env=env,
            )

            read_stream, write_stream = await exit_stack.enter_async_context(
                stdio_client(server_params)
            )

            session = await exit_stack.enter_async_context(
                ClientSession(read_stream, write_stream)
            )

            try:
                async with asyncio.timeout(policy.connect_timeout_seconds):
                    initialize_result = await session.initialize()
            except TimeoutError as exc:
                raise MCPTimeoutError(
                    f"MCP Server 初始化超时: {config.name}"
                ) from exc
            sdk_caps = getattr(initialize_result, "capabilities", None)

            capabilities = MCPServerCapabilities(
                tools=getattr(sdk_caps, "tools", None) is not None,
                resources=getattr(sdk_caps, "resources", None) is not None,
                prompts=getattr(sdk_caps, "prompts", None) is not None,
            )

        except BaseException:
            await exit_stack.aclose()
            raise

        return cls(
            server_name=config.name,
            session=session,
            exit_stack=exit_stack,
            capabilities=capabilities,
            policy=policy,
        )

    async def list_tools(self) -> tuple[MCPRemoteTool, ...]:
        response = await self._run_request(
            "tools/list",
            self._session.list_tools,
        )
        tools: list[MCPRemoteTool] = []

        for sdk_tool in response.tools:
            input_schema = getattr(sdk_tool, "inputSchema", None)
            if input_schema is None:
                input_schema = getattr(sdk_tool, "input_schema", None)

            if not isinstance(input_schema, dict):
                raise TypeError(
                    f"MCP Tool inputSchema 必须是 JSON object: {sdk_tool.name}"
                )

            tools.append(
                MCPRemoteTool(
                    name=sdk_tool.name,
                    description=sdk_tool.description or "",
                    input_schema=deepcopy(input_schema),
                )
            )

        return tuple(tools)

    async def call_tool(
        self,
        *,
        name: str,
        arguments: dict[str, Any],
    ) -> MCPCallResult:
        response = await self._run_request(
            "tools/call",
            lambda: self._session.call_tool(
                name=name,
                arguments=arguments,
            ),
        )
        is_error = getattr(response, "isError", None)
        if is_error is None:
            is_error = getattr(response, "is_error", False)

        return MCPCallResult(
            content=self._normalize_tool_content(response),
            is_error=bool(is_error),
        )

    async def list_resources(self) -> tuple[MCPRemoteResource, ...]:
        response = await self._run_request(
            "resources/list",
            self._session.list_resources,
        )
        resources: list[MCPRemoteResource] = []

        for sdk_resource in response.resources:
            mime_type = getattr(sdk_resource, "mimeType", None)
            if mime_type is None:
                mime_type = getattr(sdk_resource, "mime_type", None)

            resources.append(
                MCPRemoteResource(
                    uri=str(sdk_resource.uri),
                    name=sdk_resource.name,
                    description=sdk_resource.description or "",
                    mime_type=mime_type,
                )
            )

        return tuple(resources)

    async def read_resource(
        self,
        *,
        uri: str,
    ) -> tuple[MCPResourceContent, ...]:
        response = await self._run_request(
            "resources/read",
            lambda: self._session.read_resource(uri),
        )
        contents: list[MCPResourceContent] = []

        for sdk_content in response.contents:
            mime_type = getattr(sdk_content, "mimeType", None)
            if mime_type is None:
                mime_type = getattr(sdk_content, "mime_type", None)

            contents.append(
                MCPResourceContent(
                    uri=str(sdk_content.uri),
                    mime_type=mime_type,
                    text=getattr(sdk_content, "text", None),
                    blob=getattr(sdk_content, "blob", None),
                )
            )

        return tuple(contents)

    async def list_prompts(self) -> tuple[MCPRemotePrompt, ...]:
        response = await self._run_request(
            "prompts/list",
            self._session.list_prompts,
        )
        prompts: list[MCPRemotePrompt] = []

        for sdk_prompt in response.prompts:
            arguments: list[MCPPromptArgument] = []

            for sdk_argument in sdk_prompt.arguments or ():
                arguments.append(
                    MCPPromptArgument(
                        name=sdk_argument.name,
                        description=sdk_argument.description or "",
                        required=bool(sdk_argument.required),
                    )
                )

            prompts.append(
                MCPRemotePrompt(
                    name=sdk_prompt.name,
                    description=sdk_prompt.description or "",
                    arguments=tuple(arguments),
                )
            )

        return tuple(prompts)

    async def get_prompt(
        self,
        *,
        name: str,
        arguments: dict[str, str],
    ) -> MCPPromptResult:
        response = await self._run_request(
            "prompts/get",
            lambda: self._session.get_prompt(
                name=name,
                arguments=arguments,
            ),
        )
        messages: list[MCPPromptMessage] = []

        for sdk_message in response.messages:
            role_value = getattr(sdk_message.role, "value", sdk_message.role)
            content = sdk_message.content
            text = getattr(content, "text", None)

            if not isinstance(text, str):
                raise TypeError(
                    "当前 Agent Runtime 的 MCP Prompt 只支持文本内容"
                )

            messages.append(
                MCPPromptMessage(
                    role=str(role_value),
                    text=text,
                )
            )

        return MCPPromptResult(
            description=response.description,
            messages=tuple(messages),
        )

    @staticmethod
    def _normalize_tool_content(response: Any) -> str:
        parts: list[str] = []
        blocks = getattr(response, "content", None)

        if blocks:
            for block in blocks:
                text = getattr(block, "text", None)

                if isinstance(text, str):
                    parts.append(text)
                    continue

                model_dump = getattr(block, "model_dump", None)
                if callable(model_dump):
                    parts.append(
                        json.dumps(
                            model_dump(by_alias=True, exclude_none=True),
                            ensure_ascii=False,
                            default=str,
                        )
                    )
                    continue

                parts.append(str(block))

        if parts:
            return "\n".join(parts)

        structured_content = getattr(response, "structuredContent", None)
        if structured_content is None:
            structured_content = getattr(response, "structured_content", None)

        if structured_content is not None:
            return json.dumps(
                structured_content,
                ensure_ascii=False,
                default=str,
            )

        return ""
    def _ensure_ready(self) -> None:
        if self._state != MCPClientState.READY:
            raise MCPStateError(
                f"MCP Client 当前不可调用: "
                f"server={self.server_name}, state={self._state}"
            )


    async def _run_request(
        self,
        operation: str,
        factory: Callable[[], Awaitable[T]],
    ) -> T:
        self._ensure_ready()

        async with self._semaphore:
            try:
                async with asyncio.timeout(
                    self._policy.request_timeout_seconds
                ):
                    return await factory()

            except TimeoutError as exc:
                raise MCPTimeoutError(
                    f"MCP 请求超时: "
                    f"server={self.server_name}, "
                    f"operation={operation}, "
                    f"timeout={self._policy.request_timeout_seconds}s"
                ) from exc

            except asyncio.CancelledError:
                raise

            except Exception as exc:
                self._state = MCPClientState.FAILED

                raise MCPTransportError(
                    f"MCP 请求失败: "
                    f"server={self.server_name}, "
                    f"operation={operation}, "
                    f"{type(exc).__name__}: {exc}"
                ) from exc

    async def close(self) -> None:
        if self._state == MCPClientState.CLOSED:
            return

        if self._state == MCPClientState.CLOSING:
            return

        self._state = MCPClientState.CLOSING

        try:
            await self._exit_stack.aclose()

        except asyncio.CancelledError:
            self._state = MCPClientState.FAILED
            raise

        except Exception:
            self._state = MCPClientState.FAILED
            raise

        self._state = MCPClientState.CLOSED