from app.conversation import (
    create_conversation, 
    add_message, 
    format_history
)

from app.llm import ask_llm

from app.commands import parse_calculator_command
from app.tools.calculator import calculate

def main() -> None:
    print("nanobot-rebuild")
    print("stage 3: first tool")
    print()
    print("命令:")
    print("  /calc A OP B   使用计算器")
    print("  /history       查看当前上下文")
    print("  /clear         清空当前上下文")
    print("  exit           退出程序")


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

        add_message(messages, "user", user_message)

        try:
            answer = ask_llm(messages)
        except Exception as exc:
            messages.pop()  # 移除用户消息
            print(f"\nLLM 调用失败: {exc}")
            continue
        add_message(messages, "assistant", answer)

        print(f"\nAssistant > {answer}")


if __name__ == "__main__":
    main()