from __future__ import annotations

import asyncio
from collections.abc import Iterable
from typing import Any

from app.tools.base import BaseTool, ToolResult
from app.tools.guards import ToolExecutionGuard
from app.tools.registry import ToolRegistry


class ScopedToolRegistry(ToolRegistry):
    """Read-only capability view over a global ToolRegistry.

    In addition to capability scoping, task-local guards may request
    fine-grained serialization. Calls that receive the same serialization key
    execute one-at-a-time; calls with different keys remain concurrent.
    """

    def __init__(
        self,
        *,
        parent: ToolRegistry,
        allowed_tools: Iterable[str],
        guards: Iterable[ToolExecutionGuard] = (),
    ) -> None:
        super().__init__()

        self._parent = parent
        self._allowed = frozenset(allowed_tools)
        self._guards = tuple(guards)
        self._serialization_locks: dict[tuple[int, str], asyncio.Lock] = {}

        missing = self._allowed - set(parent.names())
        if missing:
            raise ValueError(
                "ScopedToolRegistry 引用了未注册 Tool: "
                + ", ".join(sorted(missing))
            )

    @property
    def allowed_tools(self) -> frozenset[str]:
        return self._allowed

    def register(self, tool: BaseTool) -> None:
        raise RuntimeError(
            "ScopedToolRegistry 是只读能力视图，"
            "不能在子 Agent 作用域内注册新 Tool"
        )

    def get(self, name: str) -> BaseTool:
        if name not in self._allowed:
            raise PermissionError(
                f"Tool 不在当前 SubAgent Capability Scope: {name}"
            )
        return self._parent.get(name)

    def get_definitions(self) -> list[dict[str, Any]]:
        return [
            self._parent.get(name).to_schema()
            for name in self._parent.names()
            if name in self._allowed
        ]

    def _serialization_locks_for(
        self,
        *,
        name: str,
        arguments: dict[str, Any],
    ) -> list[asyncio.Lock]:
        locks: list[asyncio.Lock] = []
        for index, guard in enumerate(self._guards):
            key_fn = getattr(guard, "serialization_key", None)
            if not callable(key_fn):
                continue
            key = key_fn(name=name, arguments=arguments)
            if not isinstance(key, str) or not key:
                continue
            lock_key = (index, key)
            lock = self._serialization_locks.get(lock_key)
            if lock is None:
                # No await occurs between lookup and insertion; within one
                # asyncio event loop this is safe and deterministic.
                lock = asyncio.Lock()
                self._serialization_locks[lock_key] = lock
            locks.append(lock)
        return locks

    async def execute(
        self,
        name: str,
        arguments: dict[str, Any],
    ) -> ToolResult:
        if name not in self._allowed:
            return ToolResult.error(
                content=f"Tool 未授权给当前 SubAgent: {name}",
                error_type="TOOL_NOT_ALLOWED",
            )

        locks = self._serialization_locks_for(
            name=name,
            arguments=arguments,
        )
        acquired: list[asyncio.Lock] = []
        try:
            # Guards are iterated in a fixed order, so lock acquisition order
            # is deterministic if multiple guards ever request serialization.
            for lock in locks:
                await lock.acquire()
                acquired.append(lock)

            # Important: the guard check happens *after* serialization. A call
            # waiting behind another same-host fetch sees the latest failure
            # streak instead of a stale pre-execution snapshot.
            for guard in self._guards:
                blocked = await guard.before_execute(
                    name=name,
                    arguments=arguments,
                )
                if blocked is not None:
                    return blocked

            result = await self._parent.execute(
                name=name,
                arguments=arguments,
            )

            for guard in self._guards:
                await guard.after_execute(
                    name=name,
                    arguments=arguments,
                    result=result,
                )

            return result
        finally:
            for lock in reversed(acquired):
                lock.release()

    def names(self) -> list[str]:
        return [
            name
            for name in self._parent.names()
            if name in self._allowed
        ]
