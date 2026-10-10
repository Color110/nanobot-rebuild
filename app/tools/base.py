from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ValidationError


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
        if not self.is_error:
            return self.content

        return (
            f"ToolError[{self.error_type}]: "
            f"{self.content}"
        )


class ToolValidationError(ValueError):
    """
    Tool 参数校验失败的统一异常。

    不同 Tool 可以使用不同校验技术，
    但可预期的参数错误统一转换成该异常。
    """
class ToolExecutionError(RuntimeError):
    def __init__(self, content: str, error_type: str) -> None:
        super().__init__(content)
        self.error_type = error_type

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
    def parameters(
        self,
    ) -> dict[str, Any]:
        """
        返回提供给 LLM 的 JSON Schema。
        """
        raise NotImplementedError

    def to_schema(
        self,
    ) -> dict[str, Any]:
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

    @abstractmethod
    def validate_arguments(
        self,
        arguments: Any,
    ) -> dict[str, Any]:
        """
        校验并规范化 Tool arguments。
        """
        raise NotImplementedError

    @abstractmethod
    async def execute(
        self,
        **kwargs: Any,
    ) -> str:
        raise NotImplementedError


class PydanticTool(BaseTool):
    """
    使用 Pydantic 定义参数与校验逻辑的 Tool。
    """

    @property
    @abstractmethod
    def argument_model(
        self,
    ) -> type[BaseModel]:
        raise NotImplementedError

    @property
    def parameters(
        self,
    ) -> dict[str, Any]:
        return (
            self.argument_model
            .model_json_schema()
        )

    def validate_arguments(
        self,
        arguments: Any,
    ) -> dict[str, Any]:

        if not isinstance(
            arguments,
            dict,
        ):
            raise ToolValidationError(
                "Tool arguments 必须是 JSON object"
            )

        try:
            validated = (
                self.argument_model
                .model_validate(
                    arguments,
                    strict=True,
                )
            )

        except ValidationError as exc:
            raise ToolValidationError(
                self._format_validation_error(
                    exc
                )
            ) from exc

        return validated.model_dump()

    @staticmethod
    def _format_validation_error(
        exc: ValidationError,
    ) -> str:

        parts: list[str] = []

        for error in exc.errors():

            location = ".".join(
                str(item)
                for item in error["loc"]
            ) or "<root>"

            message = error["msg"]

            parts.append(
                f"{location}: {message}"
            )

        return "; ".join(parts)