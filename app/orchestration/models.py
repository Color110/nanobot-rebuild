from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


_TASK_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$"
_AGENT_TYPE_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$"
_TOOL_NAME_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$"


class TaskStatus(StrEnum):
    PENDING = "PENDING"
    READY = "READY"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    TIMED_OUT = "TIMED_OUT"
    CANCELLED = "CANCELLED"
    SKIPPED = "SKIPPED"


class WorkflowStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    PARTIAL_SUCCESS = "PARTIAL_SUCCESS"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class TaskBudget(BaseModel):
    """Runtime-owned hard limits for one SubAgent task."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    max_iterations: int = Field(default=6, ge=1, le=32)
    timeout_seconds: float = Field(default=60.0, gt=0, le=3600)
    max_input_tokens: int = Field(default=6000, ge=256, le=1_000_000)


class AgentSpec(BaseModel):
    """
    Runtime-owned SubAgent profile.

    Important: this object is configuration, not Planner output.
    A Planner may request an agent_type/tool, but cannot grant itself
    permissions or budgets.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    agent_type: str = Field(pattern=_AGENT_TYPE_PATTERN)
    system_prompt: str = Field(min_length=1, max_length=20_000)
    allowed_tools: frozenset[str] = Field(default_factory=frozenset)
    allowed_skills: frozenset[str] = Field(default_factory=frozenset)
    budget: TaskBudget = Field(default_factory=TaskBudget)

    @model_validator(mode="after")
    def validate_tool_names(self) -> "AgentSpec":
        import re

        for tool_name in self.allowed_tools:
            if re.fullmatch(_TOOL_NAME_PATTERN, tool_name) is None:
                raise ValueError(f"非法 Tool 名称: {tool_name}")
        return self


class PlannedTask(BaseModel):
    """Untrusted task proposal emitted by Planner/LLM."""

    model_config = ConfigDict(extra="forbid")

    task_id: str = Field(pattern=_TASK_ID_PATTERN)
    objective: str = Field(min_length=1, max_length=4000)
    agent_type: str = Field(pattern=_AGENT_TYPE_PATTERN)
    dependencies: tuple[str, ...] = ()
    requested_tools: tuple[str, ...] = ()
    required: bool = True
    input_data: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def normalize_and_validate(self) -> "PlannedTask":
        if self.task_id in self.dependencies:
            raise ValueError("Task 不能依赖自身")

        if len(set(self.dependencies)) != len(self.dependencies):
            raise ValueError("Task dependencies 不能重复")

        if len(set(self.requested_tools)) != len(self.requested_tools):
            raise ValueError("requested_tools 不能重复")

        return self


class TaskPlan(BaseModel):
    """Planner output. Runtime validation is still mandatory."""

    model_config = ConfigDict(extra="forbid")

    plan_version: str = Field(default="1")
    tasks: tuple[PlannedTask, ...] = Field(min_length=1, max_length=64)


class RuntimeTask(BaseModel):
    """Validated task owned by Runtime after policy resolution."""

    model_config = ConfigDict(extra="forbid")

    workflow_id: str = Field(min_length=1, max_length=128)
    task_id: str = Field(pattern=_TASK_ID_PATTERN)
    objective: str
    agent_type: str = Field(pattern=_AGENT_TYPE_PATTERN)
    dependencies: tuple[str, ...] = ()
    granted_tools: tuple[str, ...] = ()
    required: bool = True
    input_data: dict[str, Any] = Field(default_factory=dict)
    budget: TaskBudget
    status: TaskStatus = TaskStatus.PENDING
    attempt: int = Field(default=0, ge=0)


class TaskError(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1, max_length=128)
    message: str = Field(min_length=1, max_length=4000)
    retryable: bool = False
    ambiguous_side_effect: bool = False


class EvidenceRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: str = Field(min_length=1, max_length=512)
    ref: str | None = Field(default=None, max_length=1024)
    snippet: str | None = Field(default=None, max_length=4000)


class TaskMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    latency_ms: float | None = Field(default=None, ge=0)
    llm_calls: int = Field(default=0, ge=0)
    tool_calls: int = Field(default=0, ge=0)
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    provider_usage_complete: bool = False


class TaskResult(BaseModel):
    """Structured SubAgent result consumed by the orchestration layer."""

    model_config = ConfigDict(extra="forbid")

    workflow_id: str = Field(min_length=1, max_length=128)
    task_id: str = Field(pattern=_TASK_ID_PATTERN)
    status: TaskStatus
    summary: str = ""
    data: dict[str, Any] = Field(default_factory=dict)
    evidence: tuple[EvidenceRef, ...] = ()
    error: TaskError | None = None
    metrics: TaskMetrics = Field(default_factory=TaskMetrics)
    trace_id: str | None = Field(default=None, max_length=128)

    @model_validator(mode="after")
    def validate_terminal_result(self) -> "TaskResult":
        terminal = {
            TaskStatus.SUCCEEDED,
            TaskStatus.FAILED,
            TaskStatus.TIMED_OUT,
            TaskStatus.CANCELLED,
            TaskStatus.SKIPPED,
        }
        if self.status not in terminal:
            raise ValueError("TaskResult.status 必须是终态")

        failed = {
            TaskStatus.FAILED,
            TaskStatus.TIMED_OUT,
            TaskStatus.CANCELLED,
        }
        if self.status in failed and self.error is None:
            raise ValueError("失败终态必须包含 error")

        return self
