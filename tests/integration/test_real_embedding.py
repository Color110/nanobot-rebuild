import os

import pytest

from app.rag.embeddings import OpenAICompatibleEmbeddingProvider


_HAS_REAL_CONFIG = all(
    [
        os.getenv("EMBEDDING_API_KEY") or os.getenv("LLM_API_KEY"),
        os.getenv("EMBEDDING_MODEL"),
        os.getenv("EMBEDDING_DIMENSION"),
    ]
)


@pytest.mark.integration
@pytest.mark.skipif(
    not _HAS_REAL_CONFIG,
    reason="需要真实 Embedding API 环境变量",
)
async def test_real_embedding_provider_smoke() -> None:
    provider = OpenAICompatibleEmbeddingProvider.from_env()
    try:
        vector = await provider.embed_query("nanobot-rebuild integration test")
        assert len(vector) == provider.dimension
    finally:
        await provider.close()
