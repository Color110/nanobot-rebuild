import asyncio
from types import SimpleNamespace

import pytest

from app.rag.embeddings import (
    EmbeddingError,
    EmbeddingRetryPolicy,
    EmbeddingTraceCollector,
    OpenAICompatibleEmbeddingProvider,
)


class FlakyResource:
    def __init__(self) -> None:
        self.calls = 0

    async def create(self, **kwargs: object) -> SimpleNamespace:
        self.calls += 1
        if self.calls < 3:
            raise OSError("temporary")
        inputs = list(kwargs["input"])  # type: ignore[arg-type]
        return SimpleNamespace(
            data=[
                SimpleNamespace(index=index, embedding=[1.0, 0.0])
                for index in range(len(inputs))
            ],
            usage=SimpleNamespace(total_tokens=7),
        )


async def test_embedding_runtime_retries_and_records_content_free_trace() -> None:
    resource = FlakyResource()
    traces = EmbeddingTraceCollector()
    provider = OpenAICompatibleEmbeddingProvider(
        api_key="",
        model="test",
        dimension=2,
        client=SimpleNamespace(embeddings=resource),
        retry_policy=EmbeddingRetryPolicy(
            max_attempts=3, initial_backoff_seconds=0
        ),
        trace_collector=traces,
    )

    assert await provider.embed_query("secret query") == [1.0, 0.0]
    trace = traces.list_records()[0]

    assert resource.calls == 3
    assert trace.attempts == 3
    assert trace.success is True
    assert trace.api_usage_tokens == 7
    assert not hasattr(trace, "text")


class SlowResource:
    def __init__(self) -> None:
        self.active = 0
        self.max_active = 0

    async def create(self, **kwargs: object) -> SimpleNamespace:
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            await asyncio.sleep(0.02)
            inputs = list(kwargs["input"])  # type: ignore[arg-type]
            return SimpleNamespace(
                data=[
                    SimpleNamespace(index=index, embedding=[1.0, 0.0])
                    for index in range(len(inputs))
                ]
            )
        finally:
            self.active -= 1


async def test_embedding_runtime_limits_concurrency() -> None:
    resource = SlowResource()
    provider = OpenAICompatibleEmbeddingProvider(
        api_key="",
        model="test",
        dimension=2,
        batch_size=1,
        max_concurrency=2,
        client=SimpleNamespace(embeddings=resource),
    )

    vectors = await provider.embed_documents([str(number) for number in range(6)])

    assert len(vectors) == 6
    assert resource.max_active == 2


async def test_embedding_runtime_times_out_and_traces_failure() -> None:
    traces = EmbeddingTraceCollector()
    provider = OpenAICompatibleEmbeddingProvider(
        api_key="",
        model="test",
        dimension=2,
        timeout_seconds=0.001,
        client=SimpleNamespace(embeddings=SlowResource()),
        retry_policy=EmbeddingRetryPolicy(max_attempts=1),
        trace_collector=traces,
    )

    with pytest.raises(EmbeddingError, match="重试耗尽"):
        await provider.embed_query("query")

    assert traces.list_records()[0].success is False
    assert traces.summary()["failures"] == 1
