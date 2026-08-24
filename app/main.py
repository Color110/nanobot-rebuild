from pathlib import Path

from app.agent import run_agent_turn
from app.commands import parse_calculator_command
from app.conversation import (
    add_message,
    create_conversation,
    format_history,
)
from app.tools.calculator import (
    CalculatorTool,
    calculate,
)
from app.tools.read_file import (
    ReadTextFileTool,
)
from app.tools.registry import (
    ToolRegistry,
)

def main() -> None:
    print("nanobot-rebuild")
    print("stage 5: agent loop")
    print()
    print("命令:")
    print("  /calc A OP B   人工直接调用计算器")
    print("  /history       查看完整 Agent Context")
    print("  /clear         清空当前上下文")
    print("  /tools          查看 Agent Tools")
    print("  exit           退出程序")
    workspace = Path("workspace")
    tool_registry = ToolRegistry()  
    tool_registry.register(CalculatorTool())
    tool_registry.register(ReadTextFileTool(workspace=workspace))


    messages = create_conversation()
    while True:
        user_message = input("\nYou > ").strip()

        if not user_message:
            print("输入不能为空。")
            return

        if user_message.lower() == "exit":
            print("Bye.")
            return
        if user_message == "/history":
            print("\n当前上下文:")
            print(format_history(messages))
            print("--------------------------------")
            continue
        if user_message == "/clear":
            messages = create_conversation()
            print("\n上下文已清空。")
            continue
        if user_message == "/tools":
            print(
                "\nAvailable Tools:"
            )

            for name in (
                tool_registry.names()
            ):
                print(
                    f"  - {name}"
                )

            continue
        if user_message.startswith("/calc"):
            try:
                left, operator, right = parse_calculator_command(user_message)
                result = calculate(left, operator, right)
            except (ValueError, ZeroDivisionError) as exc:
                print(f"\n计算器命令错误: {exc}")
            print(
                f"\nCalculator > "
                f"{left:g} "
                f"{operator} "
                f"{right:g} "
                f"= {result:g}"
            )

            continue
        turn_start_index = len(messages)
        add_message(messages, "user", user_message)

        try:
            agent_result = run_agent_turn(messages, tool_registry)

        except Exception as exc:
            del messages[turn_start_index:]  # 移除用户消息和Agent的所有消息
            print(f"\nagent 调用失败: {exc}")
            continue

        if agent_result.tools_used:
            print("\n--- 工具调用 ---")
            for index,record in enumerate(agent_result.tools_used, start=1):
                status = "错误" if record.is_error else "成功"
                print(f" arguments"
                      f"{record.arguments}")
                print(
                    f"    output   : "
                    f"{record.output}"
                )

                print(
                    f"    status   : "
                    f"{status}"
                )
            print(
                "------------------------"
            )
        print(
            f"\nAgent iterations > "
            f"{agent_result.iterations}"
        )

        print(
            f"\nAssistant > "
            f"{agent_result.final_content}"
        )


if __name__ == "__main__":
    main()