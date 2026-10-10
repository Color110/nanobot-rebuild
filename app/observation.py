from __future__ import annotations

from dataclasses import dataclass

import tiktoken


_ENCODING = tiktoken.get_encoding(
    "o200k_base"
)


@dataclass(frozen=True)
class ToolObservationPolicy:
    """限制单个 Tool Result 进入 LLM 前的体积。"""

    max_tokens: int = 1200
    head_ratio: float = 0.7

    def __post_init__(self) -> None:
        if self.max_tokens < 64:
            raise ValueError(
                "max_tokens 必须至少为 64"
            )

        if not 0.0 < self.head_ratio < 1.0:
            raise ValueError(
                "head_ratio 必须位于 0 和 1 之间"
            )


@dataclass(frozen=True)
class ToolObservation:
    content: str
    original_tokens: int
    final_tokens: int
    truncated: bool

def build_tool_observation(
    text: str,
    policy: ToolObservationPolicy | None = None,
) -> ToolObservation:

    policy = (
        policy
        or ToolObservationPolicy()
    )

    tokens = _ENCODING.encode(text)
    original_tokens = len(tokens)

    if original_tokens <= policy.max_tokens:
        return ToolObservation(
            content=text,
            original_tokens=original_tokens,
            final_tokens=original_tokens,
            truncated=False,
        )

    marker = (
        "\n\n"
        "...[Tool output truncated before "
        "entering LLM context; "
        f"original={original_tokens} tokens]..."
        "\n\n"
    )

    marker_tokens = _ENCODING.encode(marker)

    remaining = (
        policy.max_tokens
        - len(marker_tokens)
    )

    head_tokens = max(
        1,
        int(
            remaining
            * policy.head_ratio
        ),
    )

    tail_tokens = (
        remaining
        - head_tokens
    )

    content = (
        _ENCODING.decode(
            tokens[:head_tokens]
        )
        + marker
        + (
            _ENCODING.decode(
                tokens[-tail_tokens:]
            )
            if tail_tokens > 0
            else ""
        )
    )

    return ToolObservation(
        content=content,
        original_tokens=original_tokens,
        final_tokens=len(
            _ENCODING.encode(content)
        ),
        truncated=True,
    )

