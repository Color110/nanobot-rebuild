import argparse

from pathlib import Path

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
from app.agent import AgentRunner
from app.agent_loop import AgentLoop

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
    runner = AgentRunner(
        provider=provider,
        tool_registry=tool_registry,
        memory_store=memory_store,
        skill_loader=skill_loader,
        context_policy=context_policy,
        concurrent_tools=True,
    )

    agent_loop = AgentLoop(
        runner=runner,
        session_manager=session_manager,
    )
    print("nanobot-rebuild")
    print("stage 14: runner / loop separation")
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
            print("Bye.")
            return

        if user_message == "/session":
            print(f"id       : {session.session_id}")
            print(f"created  : {session.created_at}")
            print(f"updated  : {session.updated_at}")
            print(f"messages : {len(session.messages)}")
            print("---------------")                       
            continue

        if user_message == "/session":
            session = session_manager.get_or_create(args.session)

            print("\n--- Session ---")
            print(f"id       : {session.session_id}")
            print(f"created  : {session.created_at}")
            print(f"updated  : {session.updated_at}")
            print(f"messages : {len(session.messages)}")
            print("---------------")

            continue
        if user_message == "/history":
            session = session_manager.get_or_create(args.session)

            print("\n--- Session History ---")
            print(format_history(session.messages))
            print("-----------------------")

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
            session = session_manager.get_or_create(args.session)

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
        
        if user_message == "/memory-clear":
            memory_store.clear()
            print("长期记忆已清空。")
            continue
        
        if user_message == "/context":
            session = session_manager.get_or_create(args.session)

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
            
        try:
            turn_result = await agent_loop.process_user_message(
                session_id=args.session,
                content=user_message,
            )
        except Exception as exc:
            print(f"\nAgent 执行失败: {exc}")
            continue

        agent_result = turn_result.run_result

        if agent_result.tools_used:
            print("\n--- Agent Tool Trace ---")

            for index, record in enumerate(
                agent_result.tools_used,
                start=1,
            ):
                status = "ERROR" if record.is_error else "OK"

                print(f"[{index}] {record.name}")
                print(f"    arguments: {record.arguments}")
                print(f"    output   : {record.output}")
                print(f"    status   : {status}")

                if record.error_type:
                    print(f"    error    : {record.error_type}")

            print("------------------------")

        stats = agent_result.context_stats

        print(
            "\nContext > "
            f"{stats.estimated_input_tokens}/{stats.max_input_tokens} tokens, "
            f"messages {stats.selected_session_messages}/{stats.total_session_messages}, "
            f"memory {stats.selected_memory_records}/{stats.total_memory_records}"
        )

        print(f"\nAgent iterations > {agent_result.iterations}")
        print(f"\nAssistant > {agent_result.final_content}")


if __name__ == "__main__":
    asyncio.run(main())