"""将知识摄取、双路索引和 RAG Tool 组装为 Runtime 组件。"""

from dataclasses import dataclass
from pathlib import Path

from app.rag.bm25 import BM25Index
from app.rag.embeddings import EmbeddingProvider
from app.rag.indexer import IndexSyncResult, IndexingPolicy, KnowledgeIndexer
from app.rag.reranker import NoOpReranker
from app.rag.retriever import HybridRetriever
from app.tools.retrieve_knowledge import RetrieveKnowledgeTool


@dataclass(frozen=True)
class RAGRuntime:
    indexer: KnowledgeIndexer
    bm25_index: BM25Index
    retriever: HybridRetriever
    tool: RetrieveKnowledgeTool
    sync_result: IndexSyncResult


async def build_rag_runtime(
    workspace: Path,
    embedding_provider: EmbeddingProvider,
    index_path: Path | None = None,
    policy: IndexingPolicy | None = None,
    migrate_embedding_space: bool = False,
) -> RAGRuntime:
    knowledge_root = workspace / "knowledge"
    indexer = await KnowledgeIndexer.open(
        knowledge_root=knowledge_root,
        index_path=index_path or workspace / "rag" / "vector-index.json",
        embedding_provider=embedding_provider,
        policy=policy,
        migrate_embedding_space=migrate_embedding_space,
    )
    sync_result = await indexer.sync()
    bm25_index = BM25Index()
    bm25_index.rebuild(indexer.index.chunks())
    retriever = HybridRetriever(
        embedding_provider=embedding_provider,
        vector_index=indexer.index,
        bm25_index=bm25_index,
    )
    tool = RetrieveKnowledgeTool(
        retriever=retriever,
        reranker=NoOpReranker(),
    )
    return RAGRuntime(
        indexer=indexer,
        bm25_index=bm25_index,
        retriever=retriever,
        tool=tool,
        sync_result=sync_result,
    )
