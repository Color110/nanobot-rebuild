from pathlib import Path

import pytest

from app.rag.chunker import TokenChunker
from app.rag.embeddings import FakeEmbeddingProvider
from app.rag.indexer import IndexingBudgetError, IndexingPolicy, KnowledgeIndexer


async def test_indexer_incrementally_updates_and_removes_documents(
    tmp_path: Path,
) -> None:
    knowledge = tmp_path / "knowledge"
    knowledge.mkdir()
    source = knowledge / "facts.txt"
    source.write_text("Aurora-731 is the deployment code.", encoding="utf-8")
    indexer = await KnowledgeIndexer.open(
        knowledge_root=knowledge,
        index_path=tmp_path / "index.json",
        embedding_provider=FakeEmbeddingProvider(dimension=16),
        chunker=TokenChunker(chunk_size_tokens=8, overlap_tokens=1),
    )

    first = await indexer.sync()
    second = await indexer.sync()
    source.write_text("Aurora-900 is the new deployment code.", encoding="utf-8")
    third = await indexer.sync()
    source.unlink()
    fourth = await indexer.sync()

    assert first.changed_documents == 1 and first.embedded_chunks > 0
    assert second.unchanged_documents == 1 and second.embedded_chunks == 0
    assert third.changed_documents == 1 and third.deleted_chunks > 0
    assert fourth.documents == 0 and fourth.deleted_chunks > 0
    assert len(indexer.index) == 0


async def test_indexer_enforces_token_and_cost_budgets(tmp_path: Path) -> None:
    knowledge = tmp_path / "knowledge"
    knowledge.mkdir()
    (knowledge / "large.txt").write_text("word " * 100, encoding="utf-8")
    policy = IndexingPolicy(
        max_total_tokens=10,
        cost_per_million_tokens=100.0,
        max_estimated_cost=0.0001,
    )
    indexer = await KnowledgeIndexer.open(
        knowledge_root=knowledge,
        index_path=tmp_path / "index.json",
        embedding_provider=FakeEmbeddingProvider(),
        policy=policy,
    )

    with pytest.raises(IndexingBudgetError, match="Token 超过限制"):
        await indexer.sync()


async def test_indexer_rejects_oversized_file(tmp_path: Path) -> None:
    knowledge = tmp_path / "knowledge"
    knowledge.mkdir()
    (knowledge / "large.txt").write_text("123456", encoding="utf-8")
    indexer = await KnowledgeIndexer.open(
        knowledge_root=knowledge,
        index_path=tmp_path / "index.json",
        embedding_provider=FakeEmbeddingProvider(),
        policy=IndexingPolicy(max_file_size_bytes=5),
    )

    with pytest.raises(ValueError, match="超过大小限制"):
        await indexer.sync()
