import argparse

from pathlib import Path

from app.agent import run_agent_turn
from app.commands import (
    parse_calculator_command,
)
from app.conversation import (
    add_message,
    format_history,
)
from app.session import (
    SessionManager,
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

def parse_args() -> argparse.Namespace:

    parser = argparse.ArgumentParser(
        description=(
            "nanobot-rebuild "
            "Stage 8"
        )
    )

    parser.add_argument(
        "--session",
        default="default",
        help=(
            "Session ID，"
            "默认使用 default"
        ),
    )

    parser.add_argument(
        "--sessions-dir",
        default="runtime/sessions",
        help=(
            "Session 持久化目录"
        ),
    )

    return parser.parse_args()

def main() -> None:

    args = parse_args()
    workspace = Path("workspace")

    session_manager = SessionManager(Path(args.sessions_dir))

    existed = session_manager.exists(args.session)

    session = session_manager.get_or_create(args.session)

    messages = session.messages
    tool_registry = ToolRegistry()  
    tool_registry.register(CalculatorTool())
    tool_registry.register(ReadTextFileTool(workspace=workspace))

    print("nanobot-rebuild")
    print("stage 8: session persistence")
    print(f"session: {session.session_id}")
    print("status : "+ ("RESTORED" if existed else "NEW"))
    print(f"messages: {len(messages)}")
    print("命令:")
    print("  /session        查看当前 Session")
    print("  /sessions       查看已保存 Session")
    print("  /tools          查看 Agent Tools")
    print("  /history        查看完整 Agent Context")
    print("  /clear          清空当前 Session")
    print("  /calc A OP B    人工调用计算器")
    print("  exit            退出程序")

    while True:
        user_message = input("\nYou > ").strip()

        if not user_message:
            print("输入不能为空。")
            return

        if user_message.lower() == "exit":
            session_manager.save(session)
            print("Session 已保存。")
            print("Bye.")
            return

        if user_message == "/session":
            print(f"id       : {session.session_id}")
            print(f"created  : {session.created_at}")
            print(f"updated  : {session.updated_at}")
            print(f"messages : {len(session.messages)}")
            print("---------------")                       
            continue

        if user_message == "/sessions":
            session_ids = session_manager.list_session_ids()
            print("\nSaved Sessions:")
            if not session_ids:
                print("  (none)")
            else:
                for session_id in session_ids:
                    print(f"  - {session_id}")
            session_ids = (
                session_manager
                .list_session_ids()
            )
            continue    
        if user_message == "/history":
            print("\n--- Current Context ---")
            print(format_history(messages))
            print("--------------------------------")
            continue

        if user_message == "/clear":
            session.clear()
            messages = session.messages
            session_manager.save(session)
            print("当前 Session 已清空并保存。")
            continue

        if user_message == "/tools":
            print("\nAvailable Tools:")
            for name in (tool_registry.names()):
                print(f"  - {name}")
            continue

        if user_message.startswith("/calc"):
            try:
                left, operator, right = parse_calculator_command(user_message)
                result = calculate(left, operator, right)
            except (ValueError, ZeroDivisionError) as exc:
                print(f"\nCalculator Error > {exc}")
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

        session_manager.save(session)

        if agent_result.tools_used:
            print("\n--- 工具调用 ---")
            for index,record in enumerate(agent_result.tools_used, start=1):
                status = "错误" if record.is_error else "成功"
                if record.error_type:
                    print(
                        f"    error    : "
                        f"{record.error_type}"
                    )
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