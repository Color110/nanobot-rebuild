# Agent 需要解决两个问题。
#     第一个：
#         我有哪些 Tool Schema 可以发送给 LLM？
#     第二个：
#         LLM 返回 name="read_text_file" 后，怎么找到这个 Python 对象？
from typing import Any
from app.tools.base import BaseTool

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
    ) -> str:
        """
        根据 Tool 名称执行对应 Tool。
        """

        tool = self.get(name)

        return tool.execute(
            **arguments
        )

    def names(self) -> list[str]:
        """
        获取当前已注册 Tool 名称。
        """

        return list(
            self._tools.keys()
        )