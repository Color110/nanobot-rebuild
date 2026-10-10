import asyncio
import json

from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from app.context import (
    ContextPolicy,
    ContextStats,
    build_runtime_context,
)
from app.memory import MemoryStore
from app.providers import (
    LLMProvider,
    ProviderResponse,
    ToolCallRequest,
)
from app.skill_selection import (
    SkillSelectionResult,
    SkillSelectionRuntime,
)
from app.observation import (
    ToolObservationPolicy,
    build_tool_observation,
)
from app.tools.registry import ToolRegistry
MAX_AGENT_ITERATIONS = 8

@dataclass
class ToolExecutionRecord:
    tool_call_id: str
    name: str
    arguments: dict[str, Any]
    output: str
    is_error: bool = False
    error_type: str | None = None
    observation_truncated: bool = False
    original_observation_tokens: int = 0


@dataclass(frozen=True)
class AgentUsage:
    """Aggregated provider-reported usage for one AgentRunner run."""

    llm_calls: int = 0
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    provider_usage_complete: bool = False

@dataclass
class AgentRunResult:
    final_content: str
    messages: list[dict[str, Any]]
    iterations: int
    tools_used: list[ToolExecutionRecord]
    context_stats: ContextStats
    skill_selection: SkillSelectionResult | None
    usage: AgentUsage
    

@dataclass(frozen=True)
class ExecutedToolCall:
    tool_message: dict[str, Any]
    record: ToolExecutionRecord


def build_assistant_tool_call_message(
    result: ProviderResponse,
) -> dict[str, Any]:
    tool_calls: list[dict[str, Any]] = []

    for tool_call in result.tool_calls:
        tool_calls.append(
            {
                "id": tool_call.id,
                "type": "function",
                "function": {
                    "name": tool_call.name,
                    "arguments": json.dumps(
                        tool_call.arguments,
                        ensure_ascii=False,
                    ),
                },
            }
        )

    return {
        "role": "assistant",
        "content": result.content or None,
        "tool_calls": tool_calls,
    }


class AgentRunner:
    """
    执行一次完整 Agent Run。

    Runner 不负责：
    - Session 加载
    - Session 保存
    - 用户身份
    - Channel
    - 消息投递

    Runner 只负责：
    Context -> LLM -> Tool -> LLM -> Final
    """

    def __init__(
        self,
        provider: LLMProvider,
        tool_registry: ToolRegistry,
        memory_store: MemoryStore | None = None,
        skill_selection_runtime: (
            SkillSelectionRuntime | None
        ) = None,
        context_policy: ContextPolicy | None = None,
        observation_policy: (
            ToolObservationPolicy | None
        ) = None,
        max_iterations: int = MAX_AGENT_ITERATIONS,
        concurrent_tools: bool = True,
    ) -> None:
        self.provider = provider
        self.tool_registry = tool_registry
        self.memory_store = memory_store

        self.skill_selection_runtime = (
            skill_selection_runtime
        )

        self.context_policy = context_policy

        self.observation_policy: ToolObservationPolicy = (
            observation_policy
            if observation_policy is not None
            else ToolObservationPolicy()
        )

        self.max_iterations = max_iterations
        self.concurrent_tools = concurrent_tools
       
    async def _execute_one_tool_call(
        self,
        tool_call: ToolCallRequest,
    ) -> ExecutedToolCall:
        # ========================================================
        # 1. 真正执行 Tool，得到 Raw Tool Result
        # ========================================================

        tool_result = await self.tool_registry.execute(
            name=tool_call.name,
            arguments=tool_call.arguments,
        )

        # ========================================================
        # 2. Raw Tool Result
        #    -> bounded LLM Observation
        #
        # 注意：
        # Raw Tool Result 和真正进入 LLM Context 的
        # Observation 是两个不同的对象。
        # ========================================================

        observation = build_tool_observation(
            tool_result.to_llm_content(),
            policy=self.observation_policy,
        )

        # ========================================================
        # 3. LLM 只能看到经过治理后的 Observation
        # ========================================================

        tool_message = {
            "role": "tool",
            "tool_call_id": tool_call.id,
            "content": observation.content,
        }

        # ========================================================
        # 4. Trace / Execution Record
        #    仍然保留原始 Tool Result
        # ========================================================

        record = ToolExecutionRecord(
            tool_call_id=tool_call.id,
            name=tool_call.name,
            arguments=tool_call.arguments,
            output=tool_result.content,
            is_error=tool_result.is_error,
            error_type=tool_result.error_type,
            observation_truncated=(
                observation.truncated
            ),
            original_observation_tokens=(
                observation.original_tokens
            ),
        )

        return ExecutedToolCall(
            tool_message=tool_message,
            record=record,
        )
    async def _execute_tool_calls(
        self,
        tool_calls: list[ToolCallRequest],
    ) -> list[ExecutedToolCall]:
        if self.concurrent_tools:
            return list(
                await asyncio.gather(
                    *[
                        self._execute_one_tool_call(tool_call)
                        for tool_call in tool_calls
                    ]
                )
            )

        results: list[ExecutedToolCall] = []

        for tool_call in tool_calls:
            results.append(
                await self._execute_one_tool_call(tool_call)
            )

        return results

    async def run(
        self,
        initial_messages: list[dict[str, Any]],
        *,
        task_text: str,
    ) -> AgentRunResult:
        """
        基于 initial_messages 完成一次 Agent Run。

        Skill Selection 是 Run-level decision：
        在进入 Agent iteration loop 之前只执行一次，
        后续所有 iteration 使用同一批 Active Skills。

        Runner 使用工作副本，
        不直接修改调用方传入的消息列表。
        """

        task_text = task_text.strip()

        if not task_text:
            raise ValueError(
                "task_text 不能为空"
            )

        messages = deepcopy(
            initial_messages
        )

        tools_used: list[
            ToolExecutionRecord
        ] = []

        last_context_stats: (
            ContextStats | None
        ) = None

        provider_input_tokens = 0
        provider_output_tokens = 0
        provider_total_tokens = 0
        provider_usage_complete = True
        llm_calls = 0

        # ========================================================
        # 1. Skill Selection
        # ========================================================

        skill_selection_result: (
            SkillSelectionResult | None
        ) = None

        if (
            self.skill_selection_runtime
            is not None
        ):
            skill_selection_result = (
                await self
                .skill_selection_runtime
                .select(
                    user_query=task_text
                )
            )

        if skill_selection_result is None:
            skill_snapshots = ()
        else:
            skill_snapshots = (
                skill_selection_result
                .snapshots
            )

        # ========================================================
        # 2. Agent Runtime Loop
        # ========================================================

        for iteration in range(
            1,
            self.max_iterations + 1,
        ):
            runtime_context = (
                build_runtime_context(
                    session_messages=messages,
                    memory_store=self.memory_store,
                    skill_snapshots=skill_snapshots,
                    policy=self.context_policy,
                )
            )

            last_context_stats = (
                runtime_context.stats
            )

            result = (
                await self.provider.complete(
                    messages=(
                        runtime_context
                        .messages
                    ),
                    tools=(
                        self.tool_registry
                        .get_definitions()
                    ),
                )
            )

            llm_calls += 1
            if result.usage is None:
                provider_usage_complete = False
            else:
                if result.usage.input_tokens is None:
                    provider_usage_complete = False
                else:
                    provider_input_tokens += result.usage.input_tokens

                if result.usage.output_tokens is None:
                    provider_usage_complete = False
                else:
                    provider_output_tokens += result.usage.output_tokens

                if result.usage.total_tokens is None:
                    provider_usage_complete = False
                else:
                    provider_total_tokens += result.usage.total_tokens

            # ====================================================
            # Tool Calling
            # ====================================================

            if result.tool_calls:
                messages.append(
                    build_assistant_tool_call_message(
                        result
                    )
                )

                executed_calls = (
                    await self
                    ._execute_tool_calls(
                        result.tool_calls
                    )
                )

                for executed in (
                    executed_calls
                ):
                    messages.append(
                        executed.tool_message
                    )

                    tools_used.append(
                        executed.record
                    )

                continue

            # ====================================================
            # Final Answer
            # ====================================================

            final_content = (
                result.content
            )

            messages.append(
                {
                    "role": "assistant",
                    "content": final_content,
                }
            )

            if last_context_stats is None:
                raise RuntimeError(
                    "Agent 未能构建 "
                    "Runtime Context"
                )

            return AgentRunResult(
                final_content=(
                    final_content
                ),
                messages=messages,
                iterations=iteration,
                tools_used=tools_used,
                context_stats=(
                    last_context_stats
                ),
                skill_selection=(
                    skill_selection_result
                ),
                usage=AgentUsage(
                    llm_calls=llm_calls,
                    input_tokens=(
                        provider_input_tokens
                        if provider_usage_complete
                        else None
                    ),
                    output_tokens=(
                        provider_output_tokens
                        if provider_usage_complete
                        else None
                    ),
                    total_tokens=(
                        provider_total_tokens
                        if provider_usage_complete
                        else None
                    ),
                    provider_usage_complete=provider_usage_complete,
                ),
            )

        raise RuntimeError(
            "Agent 达到最大迭代次数，"
            "仍未生成最终回答。"
        )

        