import json
from dataclasses import dataclass
from typing import Any

from app.providers import LLMProvider, ProviderResponse

from app.tools.registry import ToolRegistry
from app.context import (
    ContextPolicy,
    ContextStats,
    build_runtime_context,
)
from app.providers.base import (
    LLMProvider,
    ProviderError,
    ProviderResponse,
    ToolCallRequest,
)
from app.memory import MemoryStore
from app.skills import SkillLoader
import asyncio

MAX_AGENT_ITERATIONS = 8

@dataclass
class ToolExecutionRecord:
    """
    记录一次Tool的真实执行过程。
    """

    name: str
    arguments: dict[str, Any]
    output: str
    is_error: bool = False
    error_type: str | None = None

@dataclass
class AgentRunResult:
    """
    记录一次Agent的运行过程。
    """
    final_content: str
    iterations: int
    tools_used: list[ToolExecutionRecord]
    context_stats: ContextStats

@dataclass(frozen=True)
class ExecutedToolCall:
    tool_message: dict[str, Any]
    record: ToolExecutionRecord

async def execute_one_tool_call(
    tool_registry: ToolRegistry,
    tool_call: ToolCallRequest,
    ) -> ExecutedToolCall:
    tool_result = await tool_registry.execute(
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

def build_assistant_tool_call_message(
    result:ProviderResponse,
    ) -> dict[str, Any]:
    """
    将我们的 LLMResult 转换为需要写回 messages
    的 assistant tool-call 消息。
    """
    
    tool_calls :list[dict[str, Any]] = []
    for tool_call in result.tool_calls:
        tool_calls.append({
            "id": tool_call.id,
            "type": "function",
            "function": {
                "name": tool_call.name,
                "arguments": json.dumps(tool_call.arguments,ensure_ascii=False),
            },        
        }
    )
    return {
        "role": "assistant",
        "content": result.content or None,
        "tool_calls": tool_calls,
    }

async def run_agent_turn(
    messages: list[dict[str, Any]],
    provider: LLMProvider,
    tool_registry: ToolRegistry,
    memory_store: MemoryStore | None = None,
    skill_loader: SkillLoader | None = None,
    context_policy: ContextPolicy | None = None,
    max_iterations: int = MAX_AGENT_ITERATIONS,
    concurrent_tools: bool = True,
    ) -> AgentRunResult:
    """
    运行一次Agent的完整循环，直到达到最大迭代次数或没有工具调用。

    Args:
        messages (list[dict[str, Any]]): 当前的对话上下文。
        tool_registry (ToolRegistry): 工具注册表。
        max_iterations (int): 最大迭代次数。
    """

    tools_used: list[ToolExecutionRecord] = []
    last_context_stats: ContextStats | None = None

    for iteration in range(1, max_iterations + 1):
        runtime_context  = (
            build_runtime_context(
                session_messages=messages,
                memory_store=memory_store,
                skill_loader=skill_loader,
                policy=context_policy,
            )
        )
        last_context_stats = runtime_context.stats
        result =await provider.complete(
            messages=runtime_context.messages,
            tools=tool_registry.get_definitions(),
        )
        # result = ask_llm(runtime_context.messages, tools=tool_registry.get_definitions())
        if result.tool_calls:
            assistant_tool_message = (build_assistant_tool_call_message(result))
            messages.append(assistant_tool_message)
            if concurrent_tools:
                executed_calls = await asyncio.gather(
                    *[
                        execute_one_tool_call(
                            tool_registry,
                            tool_call,
                        )
                        for tool_call in result.tool_calls
                    ]
                )
            else:
                executed_calls = []

                for tool_call in result.tool_calls:
                    executed_calls.append(
                        await execute_one_tool_call(
                            tool_registry,
                            tool_call,
                        )
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
            iterations=iteration,
            tools_used=tools_used,
            context_stats=last_context_stats,
        )

    raise RuntimeError(
        "Agent 达到最大迭代次数，仍未生成最终回答。"
    )

