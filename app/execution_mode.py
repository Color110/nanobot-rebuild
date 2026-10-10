from enum import StrEnum


class ExecutionMode(StrEnum):
    """Top-level execution path for one user turn."""

    SINGLE = "single"
    ORCHESTRATED = "orchestrated"
