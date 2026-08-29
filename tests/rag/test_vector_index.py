from pathlib import Path

import pytest

from app.rag.document import Chunk
from app.rag.embeddings import EmbeddingSpace, FakeEmbeddingProvider
from app.rag.vector_index import (
    IndexMigrationRequiredError,
    InMemoryVectorIndex,
)


def make_chunk(chunk_id: str, document_id: str = "doc-1") -> Chunk:
    return Chunk(
        id=chunk_id,
        document_id=document_id,
        source=f"{document_id}.txt",
        text=f"content {chunk_id}",
        index=0,
        token_count=2,
        start_token=0,
        end_token=2,
    )


def test_vector_index_searches_by_cosine_and_supports_delete() -> None:
    index = InMemoryVectorIndex(EmbeddingSpace("fake", "m", 2))
    first = make_chunk("chunk-a")
    second = make_chunk("chunk-b", "doc-2")
    update = index.upsert([first, second], [[1.0, 0.0], [0.0, 1.0]])

    results = index.search([0.9, 0.1], top_k=2)

    assert update.added == 2
    assert [result.chunk.id for result in results] == ["chunk-a", "chunk-b"]
    assert results[0].retrieval_method == "vector"
    assert index.delete_document("doc-1") == 1
    assert len(index) == 1


async def test_vector_index_persists_and_rejects_space_mismatch(
    tmp_path: Path,
) -> None:
    path = tmp_path / "index.json"
    space = EmbeddingSpace("fake", "m", 2)
    index = InMemoryVectorIndex(space)
    index.upsert([make_chunk("chunk-a")], [[1.0, 0.0]])
    await index.save(path)

    restored = await InMemoryVectorIndex.load(path, expected_space=space)

    assert len(restored) == 1
    assert restored.search([1.0, 0.0], 1)[0].chunk.id == "chunk-a"
    with pytest.raises(IndexMigrationRequiredError, match="模型已变化"):
        await InMemoryVectorIndex.load(
            path, expected_space=EmbeddingSpace("fake", "new-model", 2)
        )


async def test_vector_index_can_migrate_embedding_space() -> None:
    index = InMemoryVectorIndex(EmbeddingSpace("old", "old", 2))
    index.upsert([make_chunk("chunk-a")], [[1.0, 0.0]])
    provider = FakeEmbeddingProvider(dimension=8)

    await index.migrate_embeddings(provider)

    assert index.space == provider.space
    assert len(index.search(await provider.embed_query("content chunk-a"), 1)) == 1


def test_vector_index_handles_one_thousand_entries() -> None:
    index = InMemoryVectorIndex(EmbeddingSpace("fake", "stress", 4))
    chunks = [make_chunk(f"chunk-{number}", f"doc-{number}") for number in range(1000)]
    vectors = [[1.0, float(number % 7), 0.5, 0.25] for number in range(1000)]

    index.upsert(chunks, vectors)
    results = index.search([1.0, 0.0, 0.5, 0.25], top_k=10)

    assert len(index) == 1000
    assert len(results) == 10
