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
from app.memory import (
    MemoryStore,
    consolidate_session_to_memory,
)
from app.context import (
    ContextBudgetError,
    ContextPolicy,
    build_runtime_context,
)
from app.skills import SkillLoader
from app.providers import OpenAICompatibleProvider
import asyncio

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
    parser.add_argument(
        "--context-budget",
        type=int,
        default=6000,
        help="单次 LLM 输入的估算 Token Budget",
    )

    parser.add_argument(
        "--memory-budget",
        type=int,
        default=1000,
        help="Long-term Memory 最大估算 Token Budget",
    )
    parser.add_argument(
        "--skills-budget",
        type=int,
        default=1200,
        help="Skills 最大估算 Token Budget",
    )

    return parser.parse_args()

async def main() -> None:

    args = parse_args()
    workspace = Path("workspace")
    provider = OpenAICompatibleProvider.from_env()
    memory_store = MemoryStore(workspace=workspace)
    skill_loader = SkillLoader(workspace=workspace)
    session_manager = SessionManager(Path(args.sessions_dir))

    existed = session_manager.exists(args.session)

    session = session_manager.get_or_create(args.session)

    messages = session.messages
    tool_registry = ToolRegistry()  
    tool_registry.register(CalculatorTool())
    tool_registry.register(ReadTextFileTool(workspace=workspace))
    context_policy = ContextPolicy(
        max_input_tokens=args.context_budget,
        memory_budget_tokens=args.memory_budget,
        skills_budget_tokens=args.skills_budget,
    )

    print("nanobot-rebuild")
    print("stage 13: async runtime")
    print(f"session : {session.session_id}")
    print(f"status  : {'RESTORED' if existed else 'NEW'}")
    print(f"messages: {len(messages)}")
    print(f"provider: {provider.name}")
    print(f"model   : {provider.model}")
    print("命令:")
    print("  /session        查看当前 Session")
    print("  /sessions       查看已保存 Session")
    print("  /provider       查看当前模型 Provider")
    print("  /tools          查看 Agent Tools")
    print("  /skills         查看可用 Skills")
    print("  /history        查看完整 Session History")
    print("  /context        查看本轮 Runtime Context 状态")
    print("  /memory         查看长期记忆")
    print("  /memorize       从当前 Session 提取长期记忆")
    print("  /memory-clear   清空长期记忆")
    print("  /clear          清空当前 Session")
    print("  /calc A OP B    人工调用计算器")
    print("  exit            退出程序")
    while True:
        raw_input = await asyncio.to_thread(input,"\nYou > ")
        user_message = raw_input.strip()

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
        if user_message == "/memory":
            records = memory_store.list_records()
            print("\n--- Long-term Memory ---")
            if not records:
                print("(empty)")
            else:
                for record in records:
                    print(f"{record.key} = {record.value}")
                    print(f"    source : {record.source_session}")
                    print(f"    updated: {record.updated_at}")
            print("------------------------")
            continue
        if user_message == "/memorize":
            try:
                changed, candidates = await consolidate_session_to_memory(
                    messages=session.messages,
                    session_id=session.session_id,
                    store=memory_store,
                    provider=provider,
                )
            except Exception as exc:
                print(f"\nMemory consolidation failed: {exc}")
                continue

            print("\nMemory extraction:")
            if not candidates:
                print("  没有发现值得长期保存的信息。")
            else:
                for memory in candidates:
                    print(f"  - {memory.key} = {memory.value}")

            print(f"\nMemory records changed: {changed}")
            continue
        if user_message == "/memory-clear":
            memory_store.clear()
            print("长期记忆已清空。")
            continue
        if user_message == "/context":
            try:
                context_result = build_runtime_context(
                    session_messages=session.messages,
                    memory_store=memory_store,
                    skill_loader=skill_loader,
                    policy=context_policy,
                )
            except ContextBudgetError as exc:
                print(f"\nContext Error > {exc}")
                continue

            stats = context_result.stats

            print("\n--- Context Stats ---")
            print(
                f"tokens   : {stats.estimated_input_tokens}"
                f" / {stats.max_input_tokens}"
            )
            print(f"system   : {stats.system_tokens}")
            print(f"memory   : {stats.memory_tokens}")
            print(f"history  : {stats.history_tokens}")
            print(
                f"messages : {stats.selected_session_messages}"
                f" / {stats.total_session_messages}"
            )
            print(f"dropped  : {stats.dropped_session_messages}")
            print(
                f"memories : {stats.selected_memory_records}"
                f" / {stats.total_memory_records}"
            )
            print(f"skills   : {stats.skills_tokens}")

            active = (
                ", ".join(stats.active_skills)
                if stats.active_skills
                else "(none)"
            )

            print(f"active   : {active}")
            print(f"available: {stats.total_skills}")
            print("---------------------")
            continue
        if user_message == "/skills":
            skills = skill_loader.list_skills()
            print("\n--- Skills ---")
            if not skills:
                print("(none)")
            else:
                for skill in skills:
                    mode = "always" if skill.always else "on-demand"
                    print(f"{skill.name}")
                    print(f"    mode       : {mode}")
                    print(f"    description: {skill.description}")

            print("--------------")
            continue
        if user_message == "/provider":
            print("\n--- Provider ---")
            print(f"name : {provider.name}")
            print(f"model: {provider.model}")
            print("----------------")
            continue
            
        turn_start_index = len(messages)
        add_message(messages, "user", user_message)

        try:
            agent_result =await  run_agent_turn(messages, provider,tool_registry,memory_store,skill_loader,context_policy)
            stats = agent_result.context_stats

            print(
                "\nContext > "
                f"{stats.estimated_input_tokens}/{stats.max_input_tokens} tokens, "
                f"messages {stats.selected_session_messages}/{stats.total_session_messages}, "
                f"memory {stats.selected_memory_records}/{stats.total_memory_records}"
            )
        except Exception as exc:
            del messages[turn_start_index:]  # 移除用户消息和Agent的所有消息
            print(f"\nagent 调用失败le: {exc}")
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
    asyncio.run(main())