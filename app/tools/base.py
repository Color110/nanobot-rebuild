from abc import ABC, abstractmethod
from typing import Any, Protocol

class BaseTool(ABC):
    """
    所有 Tool 的统一基础接口。
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """
        Tool 唯一名称。
        """
        raise NotImplementedError

    @property
    @abstractmethod
    def description(self) -> str:
        """
        告诉 LLM：
        这个 Tool 是干什么的，
        什么场景下应该使用。
        """
        raise NotImplementedError

    @property
    @abstractmethod
    def parameters(self) -> dict[str, Any]:
        """
        Tool 参数的 JSON Schema。
        """
        raise NotImplementedError

    @abstractmethod
    def execute(self, **kwargs: Any) -> str:
        """
        真正执行 Tool。
        """
        raise NotImplementedError

    def to_schema(self) -> dict[str, Any]:
        """
        转换成 LLM Function Calling 所需格式。
        """

        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }