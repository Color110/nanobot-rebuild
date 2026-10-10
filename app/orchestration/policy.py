from dataclasses import dataclass


@dataclass(frozen=True)
class OrchestrationPolicy:
    """Runtime-owned workflow hard limits."""

    max_tasks: int = 12
    max_depth: int = 4
    max_concurrency: int = 4
    workflow_timeout_seconds: float = 300.0
    max_total_llm_calls: int = 32
    max_total_tokens: int = 100_000

    def __post_init__(self) -> None:
        if self.max_tasks <= 0:
            raise ValueError("max_tasks 必须大于 0")
        if self.max_depth <= 0:
            raise ValueError("max_depth 必须大于 0")
        if self.max_concurrency <= 0:
            raise ValueError("max_concurrency 必须大于 0")
        if self.max_concurrency > self.max_tasks:
            raise ValueError("max_concurrency 不能大于 max_tasks")
        if self.workflow_timeout_seconds <= 0:
            raise ValueError("workflow_timeout_seconds 必须大于 0")
        if self.max_total_llm_calls <= 0:
            raise ValueError("max_total_llm_calls 必须大于 0")
        if self.max_total_tokens <= 0:
            raise ValueError("max_total_tokens 必须大于 0")
