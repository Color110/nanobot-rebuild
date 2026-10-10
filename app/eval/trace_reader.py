from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


_GUARD_BLOCK_ERROR_TYPES = {
    "WEB_FETCH_REPEAT_BLOCKED",
}


@dataclass(frozen=True)
class TraceSnapshot:
    trace_id: str
    tool_names: tuple[str, ...]
    successful_tool_names: tuple[str, ...]
    tool_error_count: int
    backend_tool_error_count: int
    guard_block_count: int
    event_count: int

    @property
    def successful_tool_calls(self) -> int:
        return len(self.successful_tool_names)


class JsonlTraceReader:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def read(self, trace_id: str) -> TraceSnapshot:
        if not self.path.exists():
            return TraceSnapshot(trace_id, (), (), 0, 0, 0, 0)

        tools: list[str] = []
        successful_tools: list[str] = []
        errors = 0
        backend_errors = 0
        guard_blocks = 0
        events = 0

        with self.path.open("r", encoding="utf-8") as handle:
            for line in handle:
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if item.get("trace_id") != trace_id:
                    continue

                events += 1
                if item.get("event_type") != "TOOL_COMPLETED":
                    continue

                name = item.get("tool_name")
                status = item.get("status")
                attributes = item.get("attributes")
                error_type = (
                    attributes.get("error_type")
                    if isinstance(attributes, dict)
                    else None
                )

                if isinstance(name, str) and name:
                    tools.append(name)
                    if status == "SUCCEEDED":
                        successful_tools.append(name)

                if status == "ERROR":
                    errors += 1
                    if error_type in _GUARD_BLOCK_ERROR_TYPES:
                        guard_blocks += 1
                    else:
                        backend_errors += 1

        return TraceSnapshot(
            trace_id=trace_id,
            tool_names=tuple(tools),
            successful_tool_names=tuple(successful_tools),
            tool_error_count=errors,
            backend_tool_error_count=backend_errors,
            guard_block_count=guard_blocks,
            event_count=events,
        )
