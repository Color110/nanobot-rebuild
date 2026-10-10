from dataclasses import dataclass


@dataclass(frozen=True)
class MCPRequestPolicy:
    connect_timeout_seconds: float = 10.0
    request_timeout_seconds: float = 30.0
    max_concurrency: int = 4

    def __post_init__(self) -> None:
        if self.connect_timeout_seconds <= 0:
            raise ValueError("connect_timeout_seconds 必须大于 0")

        if self.request_timeout_seconds <= 0:
            raise ValueError("request_timeout_seconds 必须大于 0")

        if self.max_concurrency <= 0:
            raise ValueError("max_concurrency 必须大于 0")