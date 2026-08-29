"""OpenAI-Compatible 异步 Embedding Provider。"""

import asyncio
import os
import time
from collections.abc import Sequence
from typing import Any

import tiktoken
from openai import (
    APIConnectionError,
    APITimeoutError,
    AsyncOpenAI,
    InternalServerError,
    OpenAIError,
    RateLimitError,
)

from app.rag.embeddings.base import (
    EmbeddingError,
    EmbeddingProvider,
    EmbeddingSpace,
)
from app.rag.embeddings.runtime import (
    EmbeddingBatchTrace,
    EmbeddingRetryPolicy,
    EmbeddingTraceCollector,
)


_RETRIABLE_ERRORS = (
    APIConnectionError,
    APITimeoutError,
    InternalServerError,
    RateLimitError,
    OSError,
    TimeoutError,
)


class OpenAICompatibleEmbeddingProvider(EmbeddingProvider):
    """通过 OpenAI-Compatible `/embeddings` API 批量生成向量。"""

    def __init__(
        self,
        api_key: str,
        model: str,
        dimension: int,
        base_url: str | None = None,
        batch_size: int = 64,
        send_dimensions: bool = False,
        timeout_seconds: float = 30.0,
        max_concurrency: int = 4,
        retry_policy: EmbeddingRetryPolicy | None = None,
        trace_collector: EmbeddingTraceCollector | None = None,
        client: Any | None = None,
    ) -> None:
        if not api_key and client is None:
            raise ValueError("api_key 不能为空")
        if not model.strip():
            raise ValueError("model 不能为空")
        if dimension <= 0:
            raise ValueError("dimension 必须大于 0")
        if batch_size <= 0:
            raise ValueError("batch_size 必须大于 0")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds 必须大于 0")
        if max_concurrency <= 0:
            raise ValueError("max_concurrency 必须大于 0")

        super().__init__(
            EmbeddingSpace(
                provider="openai-compatible",
                model=model,
                dimension=dimension,
            )
        )
        self.batch_size = batch_size
        self.send_dimensions = send_dimensions
        self.timeout_seconds = timeout_seconds
        self.retry_policy = retry_policy or EmbeddingRetryPolicy()
        self.trace_collector = trace_collector or EmbeddingTraceCollector()
        self._semaphore = asyncio.Semaphore(max_concurrency)
        self._encoding = tiktoken.get_encoding("o200k_base")
        self._client = client or AsyncOpenAI(
            api_key=api_key,
            base_url=base_url or None,
        )

    @classmethod
    def from_env(cls) -> "OpenAICompatibleEmbeddingProvider":
        api_key = os.getenv("EMBEDDING_API_KEY") or os.getenv("LLM_API_KEY")
        model = os.getenv("EMBEDDING_MODEL")
        raw_dimension = os.getenv("EMBEDDING_DIMENSION")

        if not api_key:
            raise RuntimeError("缺少 EMBEDDING_API_KEY 或 LLM_API_KEY")
        if not model:
            raise RuntimeError("缺少环境变量 EMBEDDING_MODEL")
        if not raw_dimension:
            raise RuntimeError("缺少环境变量 EMBEDDING_DIMENSION")

        try:
            dimension = int(raw_dimension)
        except ValueError as exc:
            raise RuntimeError("EMBEDDING_DIMENSION 必须是整数") from exc

        return cls(
            api_key=api_key,
            model=model,
            dimension=dimension,
            base_url=(
                os.getenv("EMBEDDING_BASE_URL")
                or os.getenv("LLM_BASE_URL")
            ),
            batch_size=int(os.getenv("EMBEDDING_BATCH_SIZE", "64")),
            send_dimensions=(
                os.getenv("EMBEDDING_SEND_DIMENSIONS", "false").lower()
                in {"1", "true", "yes"}
            ),
            timeout_seconds=float(os.getenv("EMBEDDING_TIMEOUT_SECONDS", "30")),
            max_concurrency=int(os.getenv("EMBEDDING_MAX_CONCURRENCY", "4")),
        )

    async def _embed_batch(self, texts: list[str]) -> list[list[float]]:
        request: dict[str, Any] = {
            "model": self.model,
            "input": texts,
            "encoding_format": "float",
        }
        if self.send_dimensions:
            request["dimensions"] = self.dimension

        started = time.perf_counter()
        attempts = 0
        success = False
        error_type: str | None = None
        api_usage_tokens: int | None = None
        estimated_tokens = sum(len(self._encoding.encode(text)) for text in texts)
        try:
            while True:
                attempts += 1
                try:
                    async with self._semaphore:
                        async with asyncio.timeout(self.timeout_seconds):
                            response = await self._client.embeddings.create(**request)
                    break
                except asyncio.CancelledError:
                    raise
                except _RETRIABLE_ERRORS as exc:
                    if attempts >= self.retry_policy.max_attempts:
                        raise EmbeddingError(
                            f"Embedding API 暂时性错误，重试耗尽: {exc}"
                        ) from exc
                    await asyncio.sleep(self.retry_policy.delay_after(attempts))
                except OpenAIError as exc:
                    raise EmbeddingError(
                        f"Embedding API 非重试错误: {exc}"
                    ) from exc

            usage = getattr(response, "usage", None)
            if usage is not None:
                api_usage_tokens = getattr(usage, "total_tokens", None)

            try:
                items = list(response.data)
                indexes = [item.index for item in items]
                if sorted(indexes) != list(range(len(texts))):
                    raise EmbeddingError(
                        "Embedding API 返回了非法 index: "
                        f"expected={list(range(len(texts)))}, actual={indexes}"
                    )
                ordered = sorted(items, key=lambda item: item.index)
                vectors = [item.embedding for item in ordered]
            except (AttributeError, TypeError) as exc:
                raise EmbeddingError("Embedding API 返回了非法响应") from exc

            validated = self.validate_vectors(vectors, expected_count=len(texts))
            success = True
            return validated
        except asyncio.CancelledError:
            error_type = "CANCELLED"
            raise
        except Exception as exc:
            error_type = type(exc).__name__
            raise
        finally:
            self.trace_collector.record(
                EmbeddingBatchTrace(
                    provider=self.provider,
                    model=self.model,
                    input_count=len(texts),
                    estimated_input_tokens=estimated_tokens,
                    api_usage_tokens=api_usage_tokens,
                    duration_seconds=time.perf_counter() - started,
                    attempts=attempts,
                    success=success,
                    error_type=error_type,
                )
            )

    async def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        copied = list(texts)
        for text in copied:
            self.validate_text(text)

        batches = [
            copied[start : start + self.batch_size]
            for start in range(0, len(copied), self.batch_size)
        ]
        if not batches:
            return []
        tasks = [
            asyncio.create_task(self._embed_batch(batch)) for batch in batches
        ]
        try:
            batch_vectors = await asyncio.gather(*tasks)
        except BaseException:
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            raise
        return [vector for vectors in batch_vectors for vector in vectors]

    async def embed_query(self, text: str) -> list[float]:
        self.validate_text(text)
        return (await self._embed_batch([text]))[0]

    async def close(self) -> None:
        close = getattr(self._client, "close", None)
        if close is not None:
            await close()
