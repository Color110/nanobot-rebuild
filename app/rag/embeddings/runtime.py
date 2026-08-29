"""Embedding API 的可靠性策略与无正文 Trace。"""

from dataclasses import dataclass
from threading import Lock


@dataclass(frozen=True)
class EmbeddingRetryPolicy:
    max_attempts: int = 3
    initial_backoff_seconds: float = 0.25
    backoff_multiplier: float = 2.0
    max_backoff_seconds: float = 4.0

    def __post_init__(self) -> None:
        if self.max_attempts <= 0:
            raise ValueError("max_attempts 必须大于 0")
        if self.initial_backoff_seconds < 0 or self.max_backoff_seconds < 0:
            raise ValueError("backoff 不能小于 0")
        if self.backoff_multiplier < 1:
            raise ValueError("backoff_multiplier 不能小于 1")

    def delay_after(self, failed_attempt: int) -> float:
        return min(
            self.initial_backoff_seconds
            * self.backoff_multiplier ** max(0, failed_attempt - 1),
            self.max_backoff_seconds,
        )


@dataclass(frozen=True)
class EmbeddingBatchTrace:
    provider: str
    model: str
    input_count: int
    estimated_input_tokens: int
    api_usage_tokens: int | None
    duration_seconds: float
    attempts: int
    success: bool
    error_type: str | None


class EmbeddingTraceCollector:
    """线程安全保存调用摘要，刻意不记录知识正文和 Query。"""

    def __init__(self) -> None:
        self._records: list[EmbeddingBatchTrace] = []
        self._lock = Lock()

    def record(self, trace: EmbeddingBatchTrace) -> None:
        with self._lock:
            self._records.append(trace)

    def list_records(self) -> list[EmbeddingBatchTrace]:
        with self._lock:
            return list(self._records)

    def clear(self) -> None:
        with self._lock:
            self._records.clear()

    def summary(self) -> dict[str, int | float]:
        records = self.list_records()
        return {
            "calls": len(records),
            "failures": sum(not record.success for record in records),
            "attempts": sum(record.attempts for record in records),
            "input_count": sum(record.input_count for record in records),
            "estimated_input_tokens": sum(
                record.estimated_input_tokens for record in records
            ),
            "api_usage_tokens": sum(
                record.api_usage_tokens or 0 for record in records
            ),
            "duration_seconds": sum(
                record.duration_seconds for record in records
            ),
        }
