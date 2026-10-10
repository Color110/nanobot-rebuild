from typing import Any
from app.tools.base import (
    BaseTool,
    ToolExecutionError,
    ToolResult,
    ToolValidationError,
)


class ToolRegistry:
    """
    统一注册、查询和执行 Agent Tools。
    """

    def __init__(self) -> None:
        self._tools: dict[
            str,
            BaseTool,
        ] = {}

    def register(
        self,
        tool: BaseTool,
    ) -> None:

        if tool.name in self._tools:
            raise ValueError(
                f"Tool 已存在: {tool.name}"
            )

        self._tools[
            tool.name
        ] = tool

    def get(
        self,
        name: str,
    ) -> BaseTool:

        tool = self._tools.get(
            name
        )

        if tool is None:
            raise KeyError(
                f"未知 Tool: {name}"
            )

        return tool

    def get_definitions(
        self,
    ) -> list[
        dict[str, Any]
    ]:

        return [
            tool.to_schema()
            for tool in self._tools.values()
        ]

    async def execute(
        self,
        name: str,
        arguments: dict[
            str,
            Any,
        ],
    ) -> ToolResult:

        tool = self._tools.get(
            name
        )

        if tool is None:

            available = ", ".join(
                self.names()
            )

            return ToolResult.error(
                content=(
                    f"未知 Tool: {name}。"
                    f"可用 Tool: {available}"
                ),
                error_type=(
                    "UNKNOWN_TOOL"
                ),
            )

        try:
            validated_arguments = (
                tool.validate_arguments(
                    arguments
                )
            )

        except ToolValidationError as exc:

            return ToolResult.error(
                content=str(exc),
                error_type=(
                    "VALIDATION_ERROR"
                ),
            )

        try:
            output = await tool.execute(**validated_arguments)

        except ToolExecutionError as exc:
            return ToolResult.error(
                content=str(exc),
                error_type=exc.error_type,
            )

        except Exception as exc:
            return ToolResult.error(
                content=f"{type(exc).__name__}: {exc}",
                error_type="EXECUTION_ERROR",
            )

        return ToolResult.success(
            content=str(output)
        )

    def names(
        self,
    ) -> list[str]:

        return list(
            self._tools.keys()
        )