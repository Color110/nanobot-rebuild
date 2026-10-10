from __future__ import annotations

import asyncio
import json
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from pathlib import Path
from time import time
from typing import Any, Protocol
from uuid import uuid4


class TraceEventType(StrEnum):
    WORKFLOW_STARTED = "WORKFLOW_STARTED"
    WORKFLOW_RESUMED = "WORKFLOW_RESUMED"
    WORKFLOW_FINISHED = "WORKFLOW_FINISHED"
    WORKFLOW_FAILED = "WORKFLOW_FAILED"

    PLANNER_STARTED = "PLANNER_STARTED"
    PLANNER_ATTEMPT_STARTED = "PLANNER_ATTEMPT_STARTED"
    PLANNER_ATTEMPT_FAILED = "PLANNER_ATTEMPT_FAILED"
    PLANNER_RETRYING = "PLANNER_RETRYING"
    PLANNER_COMPLETED = "PLANNER_COMPLETED"
    VALIDATION_COMPLETED = "VALIDATION_COMPLETED"
    REDUCTION_COMPLETED = "REDUCTION_COMPLETED"

    TASK_CLAIMED = "TASK_CLAIMED"
    TASK_SKIPPED = "TASK_SKIPPED"
    TASK_RECOVERED = "TASK_RECOVERED"
    TASK_FINISHED = "TASK_FINISHED"

    SUBAGENT_STARTED = "SUBAGENT_STARTED"
    TOOL_COMPLETED = "TOOL_COMPLETED"
    SUBAGENT_FINISHED = "SUBAGENT_FINISHED"


def new_trace_id() -> str:
    return f"trace_{uuid4().hex}"


def new_event_id() -> str:
    return f"evt_{uuid4().hex}"


@dataclass(frozen=True)
class TraceEvent:
    """
    One structured observability event inside a Multi-Agent workflow.

    trace_id links the whole request/recovery attempt.
    workflow_id identifies the durable workflow instance.
    task_id / parent_task_ids reconstruct the task graph context.
    tool_call_id correlates a concrete LLM tool-call request when present.
    """

    event_id: str
    trace_id: str
    event_type: TraceEventType
    timestamp: float

    workflow_id: str | None = None
    task_id: str | None = None
    parent_task_ids: tuple[str, ...] = ()
    agent_type: str | None = None

    tool_call_id: str | None = None
    tool_name: str | None = None
    status: str | None = None

    attributes: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["event_type"] = self.event_type.value
        return payload


class TraceSink(Protocol):
    async def emit(self, event: TraceEvent) -> None: ...


class NullTraceSink:
    async def emit(self, event: TraceEvent) -> None:
        return None


class InMemoryTraceSink:
    """Useful for tests, local debugging and trace-tree inspection."""

    def __init__(self) -> None:
        self._events: list[TraceEvent] = []
        self._lock = asyncio.Lock()

    async def emit(self, event: TraceEvent) -> None:
        async with self._lock:
            self._events.append(event)

    @property
    def events(self) -> tuple[TraceEvent, ...]:
        return tuple(self._events)

    def by_trace(self, trace_id: str) -> tuple[TraceEvent, ...]:
        return tuple(
            event
            for event in self._events
            if event.trace_id == trace_id
        )


class JsonlTraceSink:
    """
    Durable local trace sink.

    JSONL is intentionally simple: one structured event per line. It is not a
    replacement for OpenTelemetry/Tempo/Jaeger, but it preserves a stable
    observability boundary so the backend can be replaced later.
    """

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = asyncio.Lock()

    async def emit(self, event: TraceEvent) -> None:
        line = json.dumps(
            event.to_dict(),
            ensure_ascii=False,
            sort_keys=True,
            default=str,
        ) + "\n"

        async with self._lock:
            await asyncio.to_thread(self._append_line, line)

    def _append_line(self, line: str) -> None:
        with self._path.open("a", encoding="utf-8") as handle:
            handle.write(line)
            handle.flush()


class CompositeTraceSink:
    def __init__(self, *sinks: TraceSink) -> None:
        self._sinks = tuple(sinks)

    async def emit(self, event: TraceEvent) -> None:
        if not self._sinks:
            return
        await asyncio.gather(
            *(sink.emit(event) for sink in self._sinks)
        )


async def emit_trace(
    sink: TraceSink,
    *,
    trace_id: str,
    event_type: TraceEventType,
    workflow_id: str | None = None,
    task_id: str | None = None,
    parent_task_ids: tuple[str, ...] = (),
    agent_type: str | None = None,
    tool_call_id: str | None = None,
    tool_name: str | None = None,
    status: str | None = None,
    attributes: dict[str, Any] | None = None,
) -> TraceEvent:
    event = TraceEvent(
        event_id=new_event_id(),
        trace_id=trace_id,
        event_type=event_type,
        timestamp=time(),
        workflow_id=workflow_id,
        task_id=task_id,
        parent_task_ids=parent_task_ids,
        agent_type=agent_type,
        tool_call_id=tool_call_id,
        tool_name=tool_name,
        status=status,
        attributes=dict(attributes or {}),
    )
    await sink.emit(event)
    return event
