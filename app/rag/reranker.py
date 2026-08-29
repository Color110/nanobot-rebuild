"""Retriever 后置重排接口。"""

from abc import ABC, abstractmethod

from app.rag.document import RetrievedChunk


class Reranker(ABC):
    @abstractmethod
    async def rerank(
        self,
        query: str,
        candidates: list[RetrievedChunk],
        top_k: int,
    ) -> list[RetrievedChunk]:
        raise NotImplementedError


class NoOpReranker(Reranker):
    """保持融合排序，作为未来 Cross-Encoder/LLM Reranker 的稳定接口。"""

    async def rerank(
        self,
        query: str,
        candidates: list[RetrievedChunk],
        top_k: int,
    ) -> list[RetrievedChunk]:
        if top_k <= 0:
            raise ValueError("top_k 必须大于 0")
        return [
            result.model_copy(update={"rank": rank})
            for rank, result in enumerate(candidates[:top_k], start=1)
        ]
