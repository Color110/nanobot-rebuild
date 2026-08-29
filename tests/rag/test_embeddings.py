from math import sqrt
from types import SimpleNamespace

import pytest

from app.rag.embeddings import (
    EmbeddingError,
    EmbeddingRetryPolicy,
    EmbeddingSpace,
    EmbeddingSpaceMismatchError,
    FakeEmbeddingProvider,
    OpenAICompatibleEmbeddingProvider,
)


async def test_fake_embedding_is_deterministic_normalized_and_shared() -> None:
    provider = FakeEmbeddingProvider(dimension=32)

    documents = await provider.embed_documents(
        ["Aurora-731 deployment code", "unrelated weather"]
    )
    query = await provider.embed_query("Aurora-731 deployment code")

    assert documents[0] == query
    assert len(query) == 32
    assert sqrt(sum(value * value for value in query)) == pytest.approx(1.0)
    assert provider.space == EmbeddingSpace(
        provider="fake",
        model="stable-feature-hash-v1",
        dimension=32,
    )


@pytest.mark.parametrize("text", ["", "  \n", "!!!"])
async def test_fake_embedding_rejects_unusable_input(text: str) -> None:
    provider = FakeEmbeddingProvider()

    with pytest.raises(ValueError):
        await provider.embed_query(text)


def test_embedding_space_rejects_incompatible_provider_model_or_dimension() -> None:
    expected = EmbeddingSpace("fake", "model-a", 3)

    with pytest.raises(EmbeddingSpaceMismatchError, match="不兼容"):
        expected.assert_compatible(EmbeddingSpace("fake", "model-b", 3))


class RecordingEmbeddingsResource:
    def __init__(self, dimension: int = 3) -> None:
        self.dimension = dimension
        self.calls: list[dict[str, object]] = []

    async def create(self, **kwargs: object) -> SimpleNamespace:
        self.calls.append(kwargs)
        inputs = list(kwargs["input"])  # type: ignore[arg-type]
        # 故意倒序，验证 Provider 根据 API index 恢复输入顺序。
        data = [
            SimpleNamespace(
                index=index,
                embedding=[float(index + 1)] * self.dimension,
            )
            for index in reversed(range(len(inputs)))
        ]
        return SimpleNamespace(data=data)


class RecordingClient:
    def __init__(self, dimension: int = 3) -> None:
        self.embeddings = RecordingEmbeddingsResource(dimension)
        self.closed = False

    async def close(self) -> None:
        self.closed = True


async def test_openai_compatible_provider_batches_and_preserves_order() -> None:
    client = RecordingClient(dimension=3)
    provider = OpenAICompatibleEmbeddingProvider(
        api_key="",
        model="embedding-test",
        dimension=3,
        batch_size=2,
        send_dimensions=True,
        client=client,
    )

    vectors = await provider.embed_documents(["a", "b", "c"])

    assert vectors == [
        [1.0, 1.0, 1.0],
        [2.0, 2.0, 2.0],
        [1.0, 1.0, 1.0],
    ]
    assert len(client.embeddings.calls) == 2
    assert client.embeddings.calls[0] == {
        "model": "embedding-test",
        "input": ["a", "b"],
        "encoding_format": "float",
        "dimensions": 3,
    }
    await provider.close()
    assert client.closed is True


async def test_openai_provider_empty_batch_does_not_call_api() -> None:
    client = RecordingClient()
    provider = OpenAICompatibleEmbeddingProvider(
        api_key="",
        model="embedding-test",
        dimension=3,
        client=client,
    )

    assert await provider.embed_documents([]) == []
    assert client.embeddings.calls == []


async def test_openai_provider_rejects_response_dimension_mismatch() -> None:
    provider = OpenAICompatibleEmbeddingProvider(
        api_key="",
        model="embedding-test",
        dimension=4,
        client=RecordingClient(dimension=3),
    )

    with pytest.raises(EmbeddingError, match="维度不匹配"):
        await provider.embed_query("query")


class InvalidIndexEmbeddingsResource:
    async def create(self, **kwargs: object) -> SimpleNamespace:
        return SimpleNamespace(
            data=[SimpleNamespace(index=7, embedding=[1.0, 2.0, 3.0])]
        )


async def test_openai_provider_rejects_invalid_response_index() -> None:
    client = SimpleNamespace(embeddings=InvalidIndexEmbeddingsResource())
    provider = OpenAICompatibleEmbeddingProvider(
        api_key="",
        model="embedding-test",
        dimension=3,
        client=client,
    )

    with pytest.raises(EmbeddingError, match="非法 index"):
        await provider.embed_query("query")


class FailingEmbeddingsResource:
    async def create(self, **kwargs: object) -> None:
        raise OSError("temporary network failure")


async def test_openai_provider_wraps_transport_error() -> None:
    client = SimpleNamespace(embeddings=FailingEmbeddingsResource())
    provider = OpenAICompatibleEmbeddingProvider(
        api_key="",
        model="embedding-test",
        dimension=3,
        retry_policy=EmbeddingRetryPolicy(max_attempts=1),
        client=client,
    )

    with pytest.raises(EmbeddingError, match="重试耗尽"):
        await provider.embed_query("query")
