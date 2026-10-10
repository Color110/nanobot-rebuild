from __future__ import annotations

from typing import Any, Protocol

from app.tools.base import ToolResult


class ToolExecutionGuard(Protocol):
    """Task-local hook around Tool execution.

    A guard may stop an execution before it reaches the backing Tool and may
    observe the final ToolResult afterwards. Guards are runtime policy, not
    model instructions.
    """

    async def before_execute(
        self,
        *,
        name: str,
        arguments: dict[str, Any],
    ) -> ToolResult | None:
        ...

    async def after_execute(
        self,
        *,
        name: str,
        arguments: dict[str, Any],
        result: ToolResult,
    ) -> None:
        ...


class ToolSerializationGuard(Protocol):
    """Optional guard capability for serializing a subset of Tool calls.

    Returning the same non-empty key for multiple calls means those calls must
    execute one-at-a-time inside the current ScopedToolRegistry. Different
    keys remain independent and can still run concurrently.
    """

    def serialization_key(
        self,
        *,
        name: str,
        arguments: dict[str, Any],
    ) -> str | None:
        ...
