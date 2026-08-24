import json
from dataclasses import dataclass
from typing import Any

from app.llm import LLMResult, ToolCallRequest, ask_llm
from app.tools.calculator import (
    CALCULATOR_TOOL_SCHEMA,
    calculate,
)
MAX_AGENT_ITERATIONS = 5

@dataclass
class ToolExecutionRecord:
    """
    记录一次Tool的真实执行过程。
    """

    name: str
    arguments: dict[str, Any]
    output: str
    is_error: bool = False

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
def execute_tool_call(
    tool_call: ToolCallRequest,
) -> str:
    """
    执行一个工具调用，并返回执行记录。
    """
    if tool_call.name == "calculator":
        result = calculate(
            left=tool_call.arguments["left"],
            operator=tool_call.arguments["operator"],
            right=tool_call.arguments["right"],
        )

        return str(result)
    
    raise ValueError(f"未知的工具调用: {tool_call.name}")

def run_agent_turn(
    messages: list[dict[str,Any]],
    max_iterations: int = MAX_AGENT_ITERATIONS,
) -> AgentRunResult:
    """
    运行一次Agent的完整循环，直到达到最大迭代次数或没有工具调用。

    Args:
        messages (list[dict[str, Any]]): 当前的对话上下文。
        max_iterations (int): 最大迭代次数。
    """
    tools_used: list[ToolExecutionRecord] = []
    for iteration in range(1, max_iterations + 1):
        result = ask_llm(messages, tools=[CALCULATOR_TOOL_SCHEMA])
        if result.tool_calls:
            assistant_tool_message = (build_assistant_tool_call_message(result))
            messages.append(assistant_tool_message)
            for tool_call in result.tool_calls:
                try:
                    tool_output = execute_tool_call(tool_call)
                    is_error = False
                except Exception as exc:
                    tool_output = (
                        "ToolError: "
                        f"{type(exc).__name__}: "
                        f"{exc}"
                    )
                    is_error = True
                messages.append({
                    "role": "tool",
                    "tool_call_id": (tool_call.id),
                    "content": tool_output,
                })
                tools_used.append(
                    ToolExecutionRecord(
                        name=tool_call.name,
                        arguments=(tool_call.arguments),
                        output=tool_output,
                        is_error=is_error
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

