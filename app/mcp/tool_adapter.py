from __future__ import annotations

from typing import Any

from jsonschema import (
    SchemaError,
    ValidationError,
)
from jsonschema.validators import (
    validator_for,
)

from app.mcp.contracts import (
    MCPClient,
    MCPRemoteTool,
)
from app.mcp.naming import (
    make_mcp_tool_name,
)
from app.tools.base import (
    BaseTool,
    ToolValidationError,
)
from app.mcp.errors import (
    MCPStateError,
    MCPTimeoutError,
    MCPTransportError,
)
from app.tools.base import (
    BaseTool,
    ToolExecutionError,
    ToolValidationError,
)
from app.mcp.security import MCPToolPermission, MCPToolRisk


class MCPToolAdapter(BaseTool):
    """
    将一个远程 MCP Tool
    适配成 Agent Runtime 的普通 Tool。
    """

    def __init__(
        self,
        *,
        client: MCPClient,
        remote_tool: MCPRemoteTool,
        permission: MCPToolPermission,
        max_result_chars: int,
    ) -> None:
        self._client = client
        self._remote_tool = remote_tool
        self._permission = permission
        self._max_result_chars = max_result_chars

        self._name = make_mcp_tool_name(
            server_name=client.server_name,
            tool_name=remote_tool.name,
        )

        validator_cls = validator_for(remote_tool.input_schema)

        try:
            validator_cls.check_schema(remote_tool.input_schema)
        except SchemaError as exc:
            raise ValueError(
                f"MCP Tool Schema 非法: {remote_tool.name}: {exc.message}"
            ) from exc

        self._validator = validator_cls(remote_tool.input_schema)


    @property
    def name(
        self,
    ) -> str:

        return self._name


    @property
    def description(
        self,
    ) -> str:

        return self._remote_tool.description


    @property
    def parameters(
        self,
    ) -> dict[str, Any]:

        return self._remote_tool.input_schema


    @property
    def remote_name(
        self,
    ) -> str:

        return self._remote_tool.name


    def validate_arguments(
        self,
        arguments: Any,
    ) -> dict[str, Any]:

        if not isinstance(
            arguments,
            dict,
        ):
            raise ToolValidationError(
                "MCP Tool arguments "
                "必须是 JSON object"
            )

        errors = sorted(
            self._validator
            .iter_errors(arguments),
            key=lambda error: list(
                error.absolute_path
            ),
        )

        if errors:

            messages: list[str] = []

            for error in errors:

                path = ".".join(
                    str(part)
                    for part
                    in error.absolute_path
                )

                if not path:
                    path = "<root>"

                messages.append(
                    f"{path}: "
                    f"{error.message}"
                )

            raise ToolValidationError(
                "; ".join(messages)
            )

        return dict(arguments)


    async def execute(self, **kwargs: Any) -> str:
        if (
            self._permission.risk == MCPToolRisk.HIGH_RISK
            or self._permission.require_confirmation
        ):
            raise ToolExecutionError(
                "该 MCP Tool 属于高风险操作，必须经过 Host/Workflow 用户确认后执行",
                "MCP_CONFIRMATION_REQUIRED",
            )

        try:
            result = await self._client.call_tool(
                name=self._remote_tool.name,
                arguments=dict(kwargs),
            )
        except MCPTimeoutError as exc:
            raise ToolExecutionError(str(exc), "MCP_TIMEOUT") from exc
        except MCPTransportError as exc:
            raise ToolExecutionError(
                str(exc),
                "MCP_TRANSPORT_ERROR",
            ) from exc
        except MCPStateError as exc:
            raise ToolExecutionError(
                str(exc),
                "MCP_STATE_ERROR",
            ) from exc

        if result.is_error:
            raise ToolExecutionError(
                result.content,
                "MCP_REMOTE_TOOL_ERROR",
            )

        if len(result.content) > self._max_result_chars:
            raise ToolExecutionError(
                (
                    f"MCP Tool 返回内容过大: "
                    f"{len(result.content)} chars，"
                    f"上限 {self._max_result_chars}"
                ),
                "MCP_RESULT_TOO_LARGE",
            )

        return result.content