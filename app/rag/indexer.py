"""知识目录增量摄取、资源预算和持久化编排。"""

import asyncio
from dataclasses import dataclass
from pathlib import Path

from app.rag.chunker import TokenChunker
from app.rag.document import Chunk, Document
from app.rag.embeddings import EmbeddingProvider
from app.rag.loaders import MarkdownDocumentLoader, TextDocumentLoader
from app.rag.vector_index import InMemoryVectorIndex


class IndexingBudgetError(RuntimeError):
    """知识摄取超过显式资源或成本预算。"""


@dataclass(frozen=True)
class IndexingPolicy:
    max_documents: int = 1_000
    max_file_size_bytes: int = 10 * 1024 * 1024
    max_chunks_per_document: int = 10_000
    max_total_tokens: int = 1_000_000
    embedding_batch_size: int = 64
    cost_per_million_tokens: float | None = None
    max_estimated_cost: float | None = None

    def __post_init__(self) -> None:
        integer_limits = (
            self.max_documents,
            self.max_file_size_bytes,
            self.max_chunks_per_document,
            self.max_total_tokens,
            self.embedding_batch_size,
        )
        if any(value <= 0 for value in integer_limits):
            raise ValueError("IndexingPolicy 的数值限制必须大于 0")
        if self.cost_per_million_tokens is not None:
            if self.cost_per_million_tokens < 0:
                raise ValueError("cost_per_million_tokens 不能小于 0")
        if self.max_estimated_cost is not None:
            if self.max_estimated_cost < 0:
                raise ValueError("max_estimated_cost 不能小于 0")
            if self.cost_per_million_tokens is None:
                raise ValueError(
                    "配置 max_estimated_cost 时必须配置 cost_per_million_tokens"
                )


@dataclass(frozen=True)
class IndexSyncResult:
    documents: int
    changed_documents: int
    unchanged_documents: int
    embedded_chunks: int
    deleted_chunks: int
    total_tokens: int
    estimated_cost: float | None


class KnowledgeIndexer:
    def __init__(
        self,
        knowledge_root: Path,
        index_path: Path,
        embedding_provider: EmbeddingProvider,
        chunker: TokenChunker | None = None,
        policy: IndexingPolicy | None = None,
        index: InMemoryVectorIndex | None = None,
    ) -> None:
        self.knowledge_root = knowledge_root.resolve()
        self.index_path = index_path
        self.embedding_provider = embedding_provider
        self.chunker = chunker or TokenChunker()
        self.policy = policy or IndexingPolicy()
        self.index = index or InMemoryVectorIndex(embedding_provider.space)
        embedding_provider.space.assert_compatible(self.index.space)

    @classmethod
    async def open(
        cls,
        knowledge_root: Path,
        index_path: Path,
        embedding_provider: EmbeddingProvider,
        chunker: TokenChunker | None = None,
        policy: IndexingPolicy | None = None,
        migrate_embedding_space: bool = False,
    ) -> "KnowledgeIndexer":
        if index_path.exists():
            if migrate_embedding_space:
                index = await InMemoryVectorIndex.load(index_path)
                if index.space != embedding_provider.space:
                    await index.migrate_embeddings(
                        embedding_provider,
                        batch_size=(policy or IndexingPolicy()).embedding_batch_size,
                    )
                    await index.save(index_path)
            else:
                index = await InMemoryVectorIndex.load(
                    index_path, expected_space=embedding_provider.space
                )
        else:
            index = InMemoryVectorIndex(embedding_provider.space)
        return cls(
            knowledge_root=knowledge_root,
            index_path=index_path,
            embedding_provider=embedding_provider,
            chunker=chunker,
            policy=policy,
            index=index,
        )

    async def _discover_paths(self) -> list[Path]:
        def discover() -> list[Path]:
            self.knowledge_root.mkdir(parents=True, exist_ok=True)
            return sorted(
                path.relative_to(self.knowledge_root)
                for path in self.knowledge_root.rglob("*")
                if path.is_file() and path.suffix.lower() in {".txt", ".md", ".markdown"}
            )

        paths = await asyncio.to_thread(discover)
        if len(paths) > self.policy.max_documents:
            raise IndexingBudgetError(
                f"文档数量超过限制: {len(paths)} > {self.policy.max_documents}"
            )
        return paths

    async def _load_documents(self, paths: list[Path]) -> list[Document]:
        text_loader = TextDocumentLoader(
            self.knowledge_root, self.policy.max_file_size_bytes
        )
        markdown_loader = MarkdownDocumentLoader(
            self.knowledge_root, self.policy.max_file_size_bytes
        )
        documents: list[Document] = []
        for path in paths:
            loader = markdown_loader if path.suffix.lower() in {".md", ".markdown"} else text_loader
            documents.append(await loader.load(path))
        return documents

    def _prepare_chunks(
        self, documents: list[Document]
    ) -> tuple[dict[str, list[Chunk]], int]:
        chunks_by_source: dict[str, list[Chunk]] = {}
        total_tokens = 0
        for document in documents:
            chunks = self.chunker.chunk(document)
            if len(chunks) > self.policy.max_chunks_per_document:
                raise IndexingBudgetError(
                    f"文档 Chunk 数超过限制: {document.source}: "
                    f"{len(chunks)} > {self.policy.max_chunks_per_document}"
                )
            total_tokens += sum(chunk.token_count for chunk in chunks)
            chunks_by_source[document.source] = chunks

        if total_tokens > self.policy.max_total_tokens:
            raise IndexingBudgetError(
                f"摄取 Token 超过限制: {total_tokens} > "
                f"{self.policy.max_total_tokens}"
            )
        return chunks_by_source, total_tokens

    def _estimate_cost(self, total_tokens: int) -> float | None:
        rate = self.policy.cost_per_million_tokens
        if rate is None:
            return None
        estimated = total_tokens / 1_000_000 * rate
        maximum = self.policy.max_estimated_cost
        if maximum is not None and estimated > maximum:
            raise IndexingBudgetError(
                f"预计 Embedding 成本超过限制: {estimated:.6f} > {maximum:.6f}"
            )
        return estimated

    async def sync(self) -> IndexSyncResult:
        paths = await self._discover_paths()
        documents = await self._load_documents(paths)
        chunks_by_source, total_tokens = self._prepare_chunks(documents)

        changed: dict[str, list[Chunk]] = {}
        unchanged_documents = 0
        for source, chunks in chunks_by_source.items():
            old_ids = {chunk.id for chunk in self.index.entries_for_source(source)}
            new_ids = {chunk.id for chunk in chunks}
            if old_ids == new_ids:
                unchanged_documents += 1
            else:
                changed[source] = chunks

        all_changed_chunks = [
            chunk for chunks in changed.values() for chunk in chunks
        ]
        embedded_tokens = sum(chunk.token_count for chunk in all_changed_chunks)
        estimated_cost = self._estimate_cost(embedded_tokens)
        all_vectors: list[list[float]] = []
        batch_size = self.policy.embedding_batch_size
        for start in range(0, len(all_changed_chunks), batch_size):
            batch = all_changed_chunks[start : start + batch_size]
            all_vectors.extend(
                await self.embedding_provider.embed_documents(
                    [chunk.text for chunk in batch]
                )
            )

        # 所有加载和 Embedding 都成功后才修改当前索引。
        deleted_chunks = 0
        offset = 0
        for source, chunks in changed.items():
            deleted_chunks += self.index.delete_source(source)
            vectors = all_vectors[offset : offset + len(chunks)]
            self.index.upsert(chunks, vectors)
            offset += len(chunks)

        live_sources = set(chunks_by_source)
        stale_sources = {
            chunk.source for chunk in self.index.chunks() if chunk.source not in live_sources
        }
        for source in stale_sources:
            deleted_chunks += self.index.delete_source(source)

        await self.index.save(self.index_path)
        return IndexSyncResult(
            documents=len(documents),
            changed_documents=len(changed),
            unchanged_documents=unchanged_documents,
            embedded_chunks=len(all_changed_chunks),
            deleted_chunks=deleted_chunks,
            total_tokens=total_tokens,
            estimated_cost=estimated_cost,
        )
