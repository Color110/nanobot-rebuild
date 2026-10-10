from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.execution_mode import ExecutionMode
from app.orchestration.models import WorkflowStatus


class FailureCategory(StrEnum):
    NONE = "NONE"
    ROUTING = "ROUTING"
    PLANNING = "PLANNING"
    VALIDATION = "VALIDATION"
    TOOL_CALLING = "TOOL_CALLING"
    TOOL_EXECUTION = "TOOL_EXECUTION"
    INEFFICIENT_TOOL_USE = "INEFFICIENT_TOOL_USE"
    CONTEXT = "CONTEXT"
    TIMEOUT = "TIMEOUT"
    DEPENDENCY = "DEPENDENCY"
    RECOVERY = "RECOVERY"
    REDUCTION = "REDUCTION"
    MODEL_OUTPUT = "MODEL_OUTPUT"
    PERFORMANCE = "PERFORMANCE"
    RUNTIME = "RUNTIME"
    UNKNOWN = "UNKNOWN"


class EvalDimension(StrEnum):
    CORRECTNESS = "correctness"
    RELIABILITY = "reliability"
    EFFICIENCY = "efficiency"


class TokenSource(StrEnum):
    PROVIDER = "provider"
    ESTIMATED = "estimated"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"


class EvalCase(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,47}$")
    prompt: str = Field(min_length=1, max_length=20_000)
    modes: tuple[ExecutionMode, ...] = (
        ExecutionMode.SINGLE,
        ExecutionMode.ORCHESTRATED,
    )
    repeats: int = Field(default=1, ge=1, le=20)
    tags: tuple[str, ...] = ()

    # Behavior / correctness requirements.
    expected_tools: tuple[str, ...] = ()
    required_successful_tools: tuple[str, ...] = ()
    forbidden_tools: tuple[str, ...] = ()
    required_text: tuple[str, ...] = ()

    # Runtime reliability requirements.
    allowed_workflow_statuses: tuple[WorkflowStatus, ...] = (
        WorkflowStatus.SUCCEEDED,
    )
    min_task_success_rate: float | None = Field(default=None, ge=0, le=1)
    max_tool_errors: int | None = Field(default=None, ge=0)
    max_backend_tool_errors: int | None = Field(default=None, ge=0)
    max_guard_blocks: int | None = Field(default=None, ge=0)

    # Efficiency/SLO requirements.
    max_tool_calls: int | None = Field(default=None, ge=0)
    max_planner_retries: int | None = Field(default=None, ge=0)
    max_total_tokens: int | None = Field(default=None, ge=0)
    max_wall_latency_ms: float | None = Field(default=None, gt=0)

    metadata: dict[str, Any] = Field(default_factory=dict)


class GradeResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    dimension: EvalDimension
    passed: bool
    score: float = Field(ge=0, le=1)
    reason: str
    failure_category: FailureCategory = FailureCategory.NONE


class EvalRunResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    case_id: str
    mode: ExecutionMode
    repeat_index: int
    tags: tuple[str, ...] = ()

    passed: bool = False
    correctness_pass: bool | None = None
    reliability_pass: bool | None = None
    efficiency_pass: bool | None = None
    execution_succeeded: bool = False
    final_content: str = ""

    workflow_id: str | None = None
    trace_id: str | None = None
    workflow_status: WorkflowStatus | None = None

    wall_latency_ms: float = Field(default=0, ge=0)
    llm_calls: int = Field(default=0, ge=0)
    tool_calls: int = Field(default=0, ge=0)
    tool_names: tuple[str, ...] = ()
    successful_tool_calls: int = Field(default=0, ge=0)
    successful_tool_names: tuple[str, ...] = ()
    tool_error_count: int = Field(default=0, ge=0)
    backend_tool_error_count: int = Field(default=0, ge=0)
    guard_block_count: int = Field(default=0, ge=0)

    planner_attempts: int = Field(default=0, ge=0)
    planner_retries: int = Field(default=0, ge=0)

    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)
    token_source: TokenSource = TokenSource.UNAVAILABLE
    estimated_cost: float | None = Field(default=None, ge=0)
    cost_currency: str | None = None

    task_count: int = Field(default=0, ge=0)
    task_success_count: int = Field(default=0, ge=0)
    task_failure_count: int = Field(default=0, ge=0)
    task_skipped_count: int = Field(default=0, ge=0)
    task_success_rate: float | None = Field(default=None, ge=0, le=1)

    grades: tuple[GradeResult, ...] = ()
    failure_category: FailureCategory = FailureCategory.NONE
    failure_detail: str | None = None
    error_type: str | None = None
    error_message: str | None = None


class ModeSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    mode: ExecutionMode
    runs: int
    passed: int
    pass_rate: float
    correctness_pass_rate: float | None = None
    reliability_pass_rate: float | None = None
    efficiency_pass_rate: float | None = None
    execution_success_rate: float = 0.0
    workflow_success_rate: float | None = None
    task_success_rate: float | None = None
    avg_wall_latency_ms: float | None = None
    p50_wall_latency_ms: float | None = None
    p95_wall_latency_ms: float | None = None
    avg_tool_calls: float | None = None
    avg_tool_errors: float | None = None
    avg_backend_tool_errors: float | None = None
    avg_guard_blocks: float | None = None
    avg_planner_attempts: float | None = None
    avg_planner_retries: float | None = None
    planner_retry_rate: float | None = None
    avg_total_tokens: float | None = None
    avg_estimated_cost: float | None = None


class EvalSuiteResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    suite_id: str
    created_at: str
    results: tuple[EvalRunResult, ...]
    by_mode: tuple[ModeSummary, ...]
    failure_counts: dict[str, int] = Field(default_factory=dict)
