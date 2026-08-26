import json
from dataclasses import dataclass
from typing import Any

from app.llm import LLMResult, ToolCallRequest, ask_llm
from app.tools.registry import ToolRegistry
from app.context import build_runtime_messages
from app.memory import MemoryStore

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

def build_assistant_tool_call_message(
    result:LLMResult,
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

def run_agent_turn(
    messages: list[dict[str, Any]],
    tool_registry: ToolRegistry,
    memory_store: MemoryStore | None = None,
    max_iterations: int = MAX_AGENT_ITERATIONS,
) -> AgentRunResult:
    """
    运行一次Agent的完整循环，直到达到最大迭代次数或没有工具调用。

    Args:
        messages (list[dict[str, Any]]): 当前的对话上下文。
        tool_registry (ToolRegistry): 工具注册表。
        max_iterations (int): 最大迭代次数。
    """

    tools_used: list[ToolExecutionRecord] = []
    for iteration in range(1, max_iterations + 1):
        runtime_messages = (
            build_runtime_messages(
                session_messages=messages,
                memory_store=memory_store,
            )
        )
        result = ask_llm(runtime_messages, tools=tool_registry.get_definitions())
        if result.tool_calls:
            assistant_tool_message = (build_assistant_tool_call_message(result))
            messages.append(assistant_tool_message)
            for tool_call in result.tool_calls:
                tool_result = (
                    tool_registry.execute(
                        name=tool_call.name,
                        arguments=tool_call.arguments,
                    )
                )

                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": (
                            tool_call.id
                        ),
                        "content": (
                            tool_result
                            .to_llm_content()
                        ),
                    }
                )

                tools_used.append(
                    ToolExecutionRecord(
                        name=tool_call.name,
                        arguments=(
                            tool_call.arguments
                        ),
                        output=(
                            tool_result.content
                        ),
                        is_error=(
                            tool_result.is_error
                        ),
                        error_type=(
                            tool_result.error_type
                        ),
                    )
                )
            continue
        final_content = result.content 
        messages.append({
            "role": "assistant",
            "content": final_content,
        })
        return AgentRunResult(
            final_content=final_content,
            iterations=iteration,
            tools_used=tools_used,
        )
    raise RuntimeError(
        f"Agent reached max iterations ({max_iterations}) without completing."
    )

