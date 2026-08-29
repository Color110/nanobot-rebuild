"""Vector + BM25 双路召回与 Reciprocal Rank Fusion。"""

from dataclasses import dataclass

from app.rag.bm25 import BM25Index
from app.rag.document import RetrievedChunk
from app.rag.embeddings import EmbeddingProvider
from app.rag.vector_index import InMemoryVectorIndex


@dataclass(frozen=True)
class RetrievalTrace:
    query: str
    vector_candidates: int
    bm25_candidates: int
    fused_candidates: int


class HybridRetriever:
    def __init__(
        self,
        embedding_provider: EmbeddingProvider,
        vector_index: InMemoryVectorIndex,
        bm25_index: BM25Index,
        rrf_k: int = 60,
    ) -> None:
        if rrf_k <= 0:
            raise ValueError("rrf_k 必须大于 0")
        embedding_provider.space.assert_compatible(vector_index.space)
        self.embedding_provider = embedding_provider
        self.vector_index = vector_index
        self.bm25_index = bm25_index
        self.rrf_k = rrf_k
        self.last_trace: RetrievalTrace | None = None

    async def retrieve(
        self,
        query: str,
        top_k: int = 5,
        candidate_k: int | None = None,
    ) -> list[RetrievedChunk]:
        if not query.strip():
            raise ValueError("query 不能为空")
        if top_k <= 0:
            raise ValueError("top_k 必须大于 0")
        candidate_k = candidate_k or max(top_k * 4, 20)
        if candidate_k < top_k:
            raise ValueError("candidate_k 不能小于 top_k")

        query_vector = await self.embedding_provider.embed_query(query)
        vector_results = self.vector_index.search(query_vector, candidate_k)
        bm25_results = self.bm25_index.search(query, candidate_k)

        fused_scores: dict[str, float] = {}
        chunks = {}
        methods: dict[str, set[str]] = {}
        for results in (vector_results, bm25_results):
            for result in results:
                chunk_id = result.chunk.id
                chunks[chunk_id] = result.chunk
                methods.setdefault(chunk_id, set()).add(result.retrieval_method)
                fused_scores[chunk_id] = fused_scores.get(chunk_id, 0.0) + (
                    1.0 / (self.rrf_k + result.rank)
                )

        ranked_ids = sorted(
            fused_scores,
            key=lambda chunk_id: (-fused_scores[chunk_id], chunk_id),
        )[:candidate_k]
        fused = [
            RetrievedChunk(
                chunk=chunks[chunk_id],
                score=fused_scores[chunk_id],
                retrieval_method="rrf:" + "+".join(sorted(methods[chunk_id])),
                rank=rank,
            )
            for rank, chunk_id in enumerate(ranked_ids, start=1)
        ]
        self.last_trace = RetrievalTrace(
            query=query,
            vector_candidates=len(vector_results),
            bm25_candidates=len(bm25_results),
            fused_candidates=len(fused),
        )
        return fused[:top_k]
