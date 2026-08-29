"""J1 Embedding 检查点：为知识 Chunk 和 Query 生成同空间向量。"""

import asyncio
from pathlib import Path

from app.rag.chunker import TokenChunker
from app.rag.embeddings import FakeEmbeddingProvider
from app.rag.loaders import MarkdownDocumentLoader


def dot(left: list[float], right: list[float]) -> float:
    return sum(a * b for a, b in zip(left, right, strict=True))


async def main() -> None:
    project_root = Path(__file__).resolve().parents[1]
    knowledge_root = project_root / "workspace" / "knowledge"
    document = await MarkdownDocumentLoader(knowledge_root).load(
        "private_facts.md"
    )
    chunks = TokenChunker(
        chunk_size_tokens=24,
        overlap_tokens=4,
    ).chunk(document)

    provider = FakeEmbeddingProvider(dimension=64)
    chunk_vectors = await provider.embed_documents(
        [chunk.text for chunk in chunks]
    )
    query = "Aurora-731 是什么？"
    query_vector = await provider.embed_query(query)

    print(f"embedding_space={provider.space}")
    print(f"query={query}")
    for chunk, vector in zip(chunks, chunk_vectors, strict=True):
        print(
            f"- chunk_id={chunk.id[:20]}... "
            f"similarity={dot(query_vector, vector):.4f} "
            f"source={chunk.source}"
        )


if __name__ == "__main__":
    asyncio.run(main())
