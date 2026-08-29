"""把 RAG 检索能力暴露为普通 Agent Tool。"""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.rag.citation import format_evidence
from app.rag.reranker import NoOpReranker, Reranker
from app.rag.retriever import HybridRetriever
from app.tools.base import BaseTool


class RetrieveKnowledgeArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(
        min_length=1,
        description="需要从私有知识库检索的明确问题或关键词",
    )
    top_k: int = Field(
        default=5,
        ge=1,
        le=20,
        description="最终返回的证据数量，范围 1 到 20",
    )


class RetrieveKnowledgeTool(BaseTool):
    def __init__(
        self,
        retriever: HybridRetriever,
        reranker: Reranker | None = None,
        retrieval_candidates: int = 20,
    ) -> None:
        if retrieval_candidates <= 0:
            raise ValueError("retrieval_candidates 必须大于 0")
        self.retriever = retriever
        self.reranker = reranker or NoOpReranker()
        self.retrieval_candidates = retrieval_candidates

    @property
    def name(self) -> str:
        return "retrieve_knowledge"

    @property
    def description(self) -> str:
        return (
            "检索 Agent 私有知识库。当问题涉及内部文档、项目事实、"
            "错误码、专有名词或模型可能不知道的信息时使用。"
            "回答知识库事实时只能使用返回证据，并引用 source 和 chunk_id。"
        )

    @property
    def argument_model(self) -> type[BaseModel]:
        return RetrieveKnowledgeArguments

    async def execute(self, **kwargs: Any) -> str:
        query = kwargs["query"].strip()
        top_k = kwargs["top_k"]
        candidate_k = max(self.retrieval_candidates, top_k)
        candidates = await self.retriever.retrieve(
            query=query,
            top_k=candidate_k,
            candidate_k=candidate_k,
        )
        results = await self.reranker.rerank(query, candidates, top_k)
        return format_evidence(results)
