from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.observation import ToolObservationPolicy
from app.providers import LLMProvider
from app.tools.registry import ToolRegistry

from .executor import SubAgentExecutor
from .graph import TaskPlanValidator
from .models import AgentSpec, TaskBudget
from .orchestrator import WorkflowOrchestrator
from .planner import LLMPlanner
from .policy import OrchestrationPolicy
from .reducer import DeterministicResultReducer
from .scheduler import TaskScheduler
from .store import SQLiteTaskStore
from .tracing import JsonlTraceSink, TraceSink


@dataclass(frozen=True)
class OrchestrationRuntime:
    orchestrator: WorkflowOrchestrator
    store: SQLiteTaskStore
    trace_sink: TraceSink
    agent_specs: dict[str, AgentSpec]
    policy: OrchestrationPolicy


def build_orchestration_runtime(
    *,
    provider: LLMProvider,
    tool_registry: ToolRegistry,
    workspace: Path,
    observation_policy: ToolObservationPolicy,
    context_budget_tokens: int = 6000,
) -> OrchestrationRuntime:
    """Build the production-facing local Multi-Agent runtime in one place."""

    available_tools = set(tool_registry.names())

    def existing(*names: str) -> frozenset[str]:
        return frozenset(
            name
            for name in names
            if name in available_tools
        )

    # MCP tools are already protected by MCP security policy and still pass
    # through ScopedToolRegistry at the SubAgent boundary.
    mcp_read_tools = frozenset(
        name
        for name in available_tools
        if name.startswith("mcp__")
    )

    base_budget = TaskBudget(
        max_iterations=6,
        timeout_seconds=90.0,
        max_input_tokens=context_budget_tokens,
    )

    agent_specs = {
        "researcher": AgentSpec(
            agent_type="researcher",
            system_prompt=(
                "你负责事实检索、资料读取和证据整理。"
                "优先使用 Runtime 暴露的可靠信息源，"
                "明确区分已知事实与推断。"
            ),
            allowed_tools=(
                existing(
                    "web_search",
                    "fetch_web_page",
                    "retrieve_knowledge",
                    "read_text_file",
                    "list_workspace_files",
                    "current_time",
                )
                | mcp_read_tools
            ),
            budget=base_budget,
        ),
        "analyst": AgentSpec(
            agent_type="analyst",
            system_prompt=(
                "你负责基于已有证据进行计算、比较和结构化分析。"
                "不要编造缺失数据。"
            ),
            allowed_tools=existing(
                "calculator",
                "retrieve_knowledge",
                "read_text_file",
                "current_time",
            ),
            budget=base_budget,
        ),
        "writer": AgentSpec(
            agent_type="writer",
            system_prompt=(
                "你负责基于依赖任务已经提供的证据生成最终回答。"
                "不得把未经支持的内容写成事实。"
            ),
            allowed_tools=existing(
                "read_text_file",
                "write_text_file",
            ),
            budget=base_budget,
        ),
    }

    policy = OrchestrationPolicy(
        max_tasks=8,
        max_depth=4,
        max_concurrency=3,
        workflow_timeout_seconds=300.0,
        max_total_llm_calls=32,
        max_total_tokens=100_000,
    )

    runtime_dir = workspace / "orchestration"
    runtime_dir.mkdir(parents=True, exist_ok=True)

    store = SQLiteTaskStore(
        runtime_dir / "tasks.sqlite3"
    )
    trace_sink = JsonlTraceSink(
        runtime_dir / "trace.jsonl"
    )

    planner = LLMPlanner(
        provider=provider,
        agent_specs=agent_specs,
        policy=policy,
        max_structured_retries=1,
    )
    validator = TaskPlanValidator(
        agent_specs=agent_specs,
        policy=policy,
    )
    executor = SubAgentExecutor(
        provider=provider,
        global_tool_registry=tool_registry,
        agent_specs=agent_specs,
        observation_policy=observation_policy,
        concurrent_tools=True,
        trace_sink=trace_sink,
    )
    scheduler = TaskScheduler(
        executor=executor,
        policy=policy,
        store=store,
        trace_sink=trace_sink,
    )
    orchestrator = WorkflowOrchestrator(
        planner=planner,
        validator=validator,
        scheduler=scheduler,
        reducer=DeterministicResultReducer(),
        trace_sink=trace_sink,
    )

    return OrchestrationRuntime(
        orchestrator=orchestrator,
        store=store,
        trace_sink=trace_sink,
        agent_specs=agent_specs,
        policy=policy,
    )
