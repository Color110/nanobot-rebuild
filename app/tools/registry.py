# Agent 需要解决两个问题。
#     第一个：
#         我有哪些 Tool Schema 可以发送给 LLM？
#     第二个：
#         LLM 返回 name="read_text_file" 后，怎么找到这个 Python 对象？
from typing import Any
from app.tools.base import BaseTool, ToolResult
from pydantic import ValidationError

class ToolRegistry:
    """
    统一注册、查询和执行 Agent Tools。
    """
    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

    def register(
        self,
        tool: BaseTool,
    ) -> None:
        """
        注册一个 Tool。
        """

        if tool.name in self._tools:
            raise ValueError(
                f"Tool 已存在: {tool.name}"
            )

        self._tools[tool.name] = tool

    def get(
        self,
        name: str,
    ) -> BaseTool:
        """
        根据名称获取 Tool。
        """

        tool = self._tools.get(name)

        if tool is None:
            raise KeyError(
                f"未知 Tool: {name}"
            )

        return tool

    def get_definitions(
        self,
    ) -> list[dict[str, Any]]:
        """
        获取所有 Tool 的 LLM Schema。
        """

        return [
            tool.to_schema()
            for tool in self._tools.values()
        ]

    def execute(
        self,
        name: str,
        arguments: dict[str, Any],
    ) -> ToolResult:
        """
        根据 Tool 名称执行对应 Tool。
        """

        tool = self._tools.get(name)

        if tool is None:
            available = ", ".join(self.names())
            return ToolResult.error(
                content=(
                    f"未知 Tool: {name}。可用 Tool: {available}"
                    ),
                    error_type="UNKNOWN_TOOL"
            )
        
        try:
            validated_arguments = (
                tool.validate_arguments(
                    arguments
                )
            )
        except ValidationError as exc:

            return ToolResult.error(
                content=(
                    self._format_validation_error(
                        exc
                    )
                ),
                error_type="VALIDATION_ERROR",
            )

        except TypeError as exc:

            return ToolResult.error(
                content=str(exc),
                error_type="VALIDATION_ERROR",
            )

        try:
            output = tool.execute(
                **validated_arguments
            )

        except Exception as exc:

            return ToolResult.error(
                content=(
                    f"{type(exc).__name__}: "
                    f"{exc}"
                ),
                error_type="EXECUTION_ERROR",
            )

        return ToolResult.success(
            content=str(output)
        )

    @staticmethod
    def _format_validation_error(
        exc: ValidationError,
    ) -> str:

        parts: list[str] = []

        for error in exc.errors():

            location = ".".join(
                str(item)
                for item in error["loc"]
            )

            message = error["msg"]

            parts.append(
                f"{location}: {message}"
            )

        return "; ".join(parts)

    def names(self) -> list[str]:

        return list(
            self._tools.keys()
        )

