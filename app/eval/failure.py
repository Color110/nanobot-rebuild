from __future__ import annotations

from app.context import ContextBudgetError
from app.orchestration.graph import TaskPlanValidationError
from app.orchestration.planner import PlannerOutputError
from app.orchestration.reducer import OrchestrationResult
from app.orchestration.scheduler import SchedulerInvariantError
from app.orchestration.store import TaskStoreError
from app.providers import ProviderError

from .models import FailureCategory


def classify_exception(exc: Exception) -> FailureCategory:
    if isinstance(exc, PlannerOutputError):
        # Structural Planner output is a model-output failure. Semantic DAG /
        # capability violations are classified later by TaskPlanValidator.
        return FailureCategory.MODEL_OUTPUT
    if isinstance(exc, TaskPlanValidationError):
        return FailureCategory.VALIDATION
    if isinstance(exc, ContextBudgetError):
        return FailureCategory.CONTEXT
    if isinstance(exc, TimeoutError):
        return FailureCategory.TIMEOUT
    if isinstance(exc, ProviderError):
        return FailureCategory.MODEL_OUTPUT
    if isinstance(exc, (SchedulerInvariantError, TaskStoreError)):
        return FailureCategory.RUNTIME
    return FailureCategory.UNKNOWN


def classify_orchestration_result(result: OrchestrationResult) -> tuple[FailureCategory, str | None]:
    if not result.errors:
        return FailureCategory.NONE, None

    code = result.errors[0].error.code.upper()
    detail = result.errors[0].error.message

    if "TIMEOUT" in code or "DEADLINE" in code:
        return FailureCategory.TIMEOUT, detail
    if "TOOL" in code and ("VALIDATION" in code or "NOT_ALLOWED" in code or "UNKNOWN" in code):
        return FailureCategory.TOOL_CALLING, detail
    if "TOOL" in code or "WEB_SEARCH" in code or "FETCH" in code:
        return FailureCategory.TOOL_EXECUTION, detail
    if "DEPEND" in code:
        return FailureCategory.DEPENDENCY, detail
    if "ORPHAN" in code or "LEASE" in code or "RECOVER" in code:
        return FailureCategory.RECOVERY, detail
    if "CONTEXT" in code:
        return FailureCategory.CONTEXT, detail
    if "SUBAGENT" in code:
        return FailureCategory.RUNTIME, detail
    return FailureCategory.UNKNOWN, detail
