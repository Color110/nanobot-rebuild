"""无需网络的确定性 Embedding Provider。"""

import hashlib
import math
import re
from collections import Counter
from collections.abc import Sequence

from app.rag.embeddings.base import EmbeddingProvider, EmbeddingSpace


_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_]+|[\u3400-\u9fff]")


class FakeEmbeddingProvider(EmbeddingProvider):
    """使用稳定特征哈希生成归一化向量，供测试与演示使用。"""

    def __init__(self, dimension: int = 64) -> None:
        super().__init__(
            EmbeddingSpace(
                provider="fake",
                model="stable-feature-hash-v1",
                dimension=dimension,
            )
        )

    @staticmethod
    def _tokens(text: str) -> list[str]:
        return [token.lower() for token in _TOKEN_PATTERN.findall(text)]

    def _embed(self, text: str) -> list[float]:
        self.validate_text(text)
        vector = [0.0] * self.dimension

        for token, count in Counter(self._tokens(text)).items():
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            bucket = int.from_bytes(digest[:8], "big") % self.dimension
            sign = 1.0 if digest[8] & 1 else -1.0
            vector[bucket] += sign * float(count)

        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0:
            raise ValueError("Embedding 输入不包含可索引内容")

        return [value / norm for value in vector]

    async def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._embed(text) for text in texts]

    async def embed_query(self, text: str) -> list[float]:
        return self._embed(text)
