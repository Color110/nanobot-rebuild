from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel


@dataclass(frozen=True)
class ToolResult:
    """
    Tool 的统一执行结果。
    """

    content: str
    is_error: bool = False
    error_type: str | None = None

    @classmethod
    def success(
        cls,
        content: str,
    ) -> "ToolResult":
        return cls(
            content=content,
            is_error=False,
            error_type=None,
        )

    @classmethod
    def error(
        cls,
        content: str,
        error_type: str,
    ) -> "ToolResult":
        return cls(
            content=content,
            is_error=True,
            error_type=error_type,
        )

    def to_llm_content(self) -> str:
        """
        转换成放入 role=tool 消息中的文本。
        """

        if not self.is_error:
            return self.content

        return (
            f"ToolError[{self.error_type}]: "
            f"{self.content}"
        )


class BaseTool(ABC):
    """
    所有 Agent Tool 的统一基础接口。
    """

    @property
    @abstractmethod
    def name(self) -> str:
        raise NotImplementedError

    @property
    @abstractmethod
    def description(self) -> str:
        raise NotImplementedError

    @property
    @abstractmethod
    def argument_model(
        self,
    ) -> type[BaseModel]:
        """
        Tool 参数对应的 Pydantic Model。
        """
        raise NotImplementedError

    @property
    def parameters(self) -> dict[str, Any]:
        """
        从 Pydantic Model 自动生成 JSON Schema。
        """
        return (
            self.argument_model
            .model_json_schema()
        )

    def to_schema(self) -> dict[str, Any]:
        """
        转换成 LLM Function Calling Schema。
        """

        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

    def validate_arguments(
        self,
        arguments: Any,
    ) -> dict[str, Any]:
        """
        对 LLM 返回的 Tool arguments
        进行严格运行时校验。
        """

        if not isinstance(arguments, dict):
            raise TypeError(
                "Tool arguments 必须是 JSON object"
            )

        validated = (
            self.argument_model
            .model_validate(
                arguments,
                strict=True,
            )
        )

        return validated.model_dump()

    @abstractmethod
    async def execute(
        self,
        **kwargs: Any,
    ) -> str:
        raise NotImplementedError
