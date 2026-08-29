"""Embedding Provider 抽象与向量空间约束。"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from math import isfinite
from collections.abc import Sequence


class EmbeddingError(RuntimeError):
    """Embedding 请求或响应不满足 Runtime 契约。"""


class EmbeddingSpaceMismatchError(EmbeddingError):
    """Document 与 Query 使用了不兼容的向量空间。"""


@dataclass(frozen=True)
class EmbeddingSpace:
    """唯一标识一组可以相互比较的 Embedding 向量。"""

    provider: str
    model: str
    dimension: int

    def __post_init__(self) -> None:
        if not self.provider.strip():
            raise ValueError("embedding provider 不能为空")
        if not self.model.strip():
            raise ValueError("embedding model 不能为空")
        if self.dimension <= 0:
            raise ValueError("embedding dimension 必须大于 0")

    def assert_compatible(self, other: "EmbeddingSpace") -> None:
        if self != other:
            raise EmbeddingSpaceMismatchError(
                "Embedding Space 不兼容: "
                f"expected={self}, actual={other}"
            )


class EmbeddingProvider(ABC):
    """Document 与 Query Embedding 的统一异步接口。"""

    def __init__(self, space: EmbeddingSpace) -> None:
        self._space = space

    @property
    def space(self) -> EmbeddingSpace:
        return self._space

    @property
    def provider(self) -> str:
        return self.space.provider

    @property
    def model(self) -> str:
        return self.space.model

    @property
    def dimension(self) -> int:
        return self.space.dimension

    @abstractmethod
    async def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        """批量生成文档向量，返回顺序必须与输入一致。"""

    @abstractmethod
    async def embed_query(self, text: str) -> list[float]:
        """生成查询向量，必须与 Document 使用同一个 Space。"""

    @staticmethod
    def validate_text(text: str) -> None:
        if not isinstance(text, str):
            raise TypeError("Embedding 输入必须是字符串")
        if not text.strip():
            raise ValueError("Embedding 输入不能为空")

    def validate_vectors(
        self,
        vectors: Sequence[Sequence[float]],
        expected_count: int,
    ) -> list[list[float]]:
        if len(vectors) != expected_count:
            raise EmbeddingError(
                "Embedding 响应数量不匹配: "
                f"expected={expected_count}, actual={len(vectors)}"
            )

        validated: list[list[float]] = []
        for index, vector in enumerate(vectors):
            if len(vector) != self.dimension:
                raise EmbeddingError(
                    f"Embedding[{index}] 维度不匹配: "
                    f"expected={self.dimension}, actual={len(vector)}"
                )

            try:
                converted = [float(value) for value in vector]
            except (TypeError, ValueError) as exc:
                raise EmbeddingError(
                    f"Embedding[{index}] 包含非数值元素"
                ) from exc
            if not all(isfinite(value) for value in converted):
                raise EmbeddingError(
                    f"Embedding[{index}] 包含非有限数值"
                )
            validated.append(converted)

        return validated
