import asyncio
import json
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from app.context import ContextPolicy, ContextStats, build_runtime_context
from app.memory import MemoryStore
from app.providers import LLMProvider, ProviderResponse, ToolCallRequest
from app.skills import SkillLoader
from app.tools.registry import ToolRegistry


MAX_AGENT_ITERATIONS = 8


@dataclass
class ToolExecutionRecord:
    name: str
    arguments: dict[str, Any]
    output: str
    is_error: bool = False
    error_type: str | None = None


@dataclass
class AgentRunResult:
    final_content: str
    messages: list[dict[str, Any]]
    iterations: int
    tools_used: list[ToolExecutionRecord]
    context_stats: ContextStats


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
        skill_loader: SkillLoader | None = None,
        context_policy: ContextPolicy | None = None,
        max_iterations: int = MAX_AGENT_ITERATIONS,
        concurrent_tools: bool = True,
    ) -> None:
        self.provider = provider
        self.tool_registry = tool_registry
        self.memory_store = memory_store
        self.skill_loader = skill_loader
        self.context_policy = context_policy
        self.max_iterations = max_iterations
        self.concurrent_tools = concurrent_tools

    async def _execute_one_tool_call(
        self,
        tool_call: ToolCallRequest,
    ) -> ExecutedToolCall:
        tool_result = await self.tool_registry.execute(
            name=tool_call.name,
            arguments=tool_call.arguments,
        )

        tool_message = {
            "role": "tool",
            "tool_call_id": tool_call.id,
            "content": tool_result.to_llm_content(),
        }

        record = ToolExecutionRecord(
            name=tool_call.name,
            arguments=tool_call.arguments,
            output=tool_result.content,
            is_error=tool_result.is_error,
            error_type=tool_result.error_type,
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
    ) -> AgentRunResult:
        """
        基于 initial_messages 完成一次 Agent Run。

        注意：
        Runner 使用工作副本，不直接修改调用方传入的消息列表。
        """

        messages = deepcopy(initial_messages)
        tools_used: list[ToolExecutionRecord] = []
        last_context_stats: ContextStats | None = None

        for iteration in range(1, self.max_iterations + 1):
            runtime_context = build_runtime_context(
                session_messages=messages,
                memory_store=self.memory_store,
                skill_loader=self.skill_loader,
                policy=self.context_policy,
            )

            last_context_stats = runtime_context.stats

            result = await self.provider.complete(
                messages=runtime_context.messages,
                tools=self.tool_registry.get_definitions(),
            )

            if result.tool_calls:
                messages.append(
                    build_assistant_tool_call_message(result)
                )

                executed_calls = await self._execute_tool_calls(
                    result.tool_calls
                )

                for executed in executed_calls:
                    messages.append(executed.tool_message)
                    tools_used.append(executed.record)

                continue

            final_content = result.content

            messages.append(
                {
                    "role": "assistant",
                    "content": final_content,
                }
            )

            if last_context_stats is None:
                raise RuntimeError(
                    "Agent 未能构建 Runtime Context"
                )

            return AgentRunResult(
                final_content=final_content,
                messages=messages,
                iterations=iteration,
                tools_used=tools_used,
                context_stats=last_context_stats,
            )

        raise RuntimeError(
            "Agent 达到最大迭代次数，仍未生成最终回答。"
        )