import argparse

import os

import sys



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

from app.tools.calculator import calculate

from app.memory import (

    MemoryStore,

    consolidate_session_to_memory,

)

from app.context import (

    ContextPolicy,

)

from app.skills import SkillLoader

from app.providers import OpenAICompatibleProvider

import asyncio

from app.agent import AgentRunResult,AgentRunner

from app.agent_loop import AgentLoop

from app.rag.bootstrap import build_rag_runtime

from app.rag.embeddings import (

    FakeEmbeddingProvider,

    OpenAICompatibleEmbeddingProvider,

)

from app.skill_catalog import SkillCatalog

from app.skill_activation import ActivationResolver

from app.skill_retriever import (

    SkillRetriever,

    BM25SkillRetriever,

    HybridSkillRetriever,

)

from app.search import (

    SearchTokenizer,

)



from app.skill_router import (

    SkillRouter,

)



from app.skill_router_adapter import (

    LLMProviderSkillRouterAdapter,

)



from app.skill_selection import (

    SkillSelectionRuntime,

)



from app.skill_policy import (

    SkillPolicyValidator,

    SkillRuntimePolicy,

)



from app.mcp.config import (

    StdioMCPServerConfig,

)

from app.mcp.manager import (

    MCPManager,

)

from app.mcp.sdk_client import (

    SDKMCPClient,

)

from app.mcp.security import (

    MCPSecurityPolicy,

    MCPToolPermission,

    MCPToolRisk,

)

from app.observation import (

    ToolObservationPolicy,

)

from app.execution_mode import ExecutionMode

from app.orchestration import build_orchestration_runtime

from app.tools import ToolRegistry, register_standard_tools
from app.eval import (
    EvalRunner, JsonlTraceReader, ModelPricing, load_eval_cases, save_eval_report,
)



def parse_args() -> argparse.Namespace:



    parser = argparse.ArgumentParser(

        description="nanobot-rebuild asynchronous Agent Runtime",

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

    parser.add_argument(

        "--disable-rag",

        action="store_true",

        help="不加载知识库，也不注册 retrieve_knowledge Tool",

    )

    parser.add_argument(

        "--embedding-provider",

        choices=["fake", "openai"],

        default=os.getenv("RAG_EMBEDDING_PROVIDER", "fake"),

        help="RAG Embedding Provider；默认 fake，真实运行可选择 openai",

    )

    parser.add_argument(

        "--rag-index",

        default="workspace/rag/vector-index.json",

        help="持久化向量索引路径",

    )

    parser.add_argument(

        "--migrate-rag-index",

        action="store_true",

        help="Embedding Space 变化时重新生成全部向量",

    )

    parser.add_argument(

        "--enable-mcp-demo",

        action="store_true",

        help=(

            "启动本地真实 stdio MCP Demo Server"

        ),

    )

    parser.add_argument(

        "--tool-observation-budget",

        type=int,

        default=1200,

        help=(

            "单个 Tool Result 进入 LLM Context "

            "前的最大 Token Budget"

        ),

    )

    parser.add_argument(

        "--execution-mode",

        choices=[mode.value for mode in ExecutionMode],

        default=ExecutionMode.SINGLE.value,

        help="本轮默认执行模式：single 或 orchestrated",

    )

    parser.add_argument("--eval-input-cost-per-million", type=float, default=None, help="Eval: 每百万 input tokens 单价")
    parser.add_argument("--eval-output-cost-per-million", type=float, default=None, help="Eval: 每百万 output tokens 单价")
    parser.add_argument("--eval-cost-currency", default="USD", help="Eval 成本币种标签")

    return parser.parse_args()



async def main() -> None:



    args = parse_args()

    workspace = Path("workspace")

    provider = OpenAICompatibleProvider.from_env()

    memory_store = MemoryStore(workspace=workspace)

    skill_loader = SkillLoader(workspace=workspace)



    # ============================================================

    # Skill Catalog

    # ============================================================



    skill_catalog = SkillCatalog(skill_loader.list_skills())



    # ============================================================

    # Skill Vector Retriever

    # ============================================================



    skill_embedding_provider = OpenAICompatibleEmbeddingProvider.from_env()



    vector_skill_retriever = SkillRetriever(

        catalog=skill_catalog,

        embedding_provider=skill_embedding_provider,

    )



    await vector_skill_retriever.build_index()



    # ============================================================

    # Skill BM25 Retriever

    # ============================================================



    skill_tokenizer = SearchTokenizer()



    bm25_skill_retriever = BM25SkillRetriever(

        catalog=skill_catalog,

        tokenizer=skill_tokenizer,

    )



    bm25_skill_retriever.build_index()



    # ============================================================

    # Hybrid / RRF Retriever

    # ============================================================



    skill_retriever = HybridSkillRetriever(

        vector_retriever=vector_skill_retriever,

        bm25_retriever=bm25_skill_retriever,

        rrf_k=60,

        candidate_k=max(1, len(skill_catalog.descriptors())),

    )



    # ============================================================

    # LLM Skill Router

    # ============================================================



    skill_router_model = LLMProviderSkillRouterAdapter(provider=provider)



    skill_router = SkillRouter(model=skill_router_model)



    # ============================================================

    # Activation Resolver

    # ============================================================



    activation_resolver = ActivationResolver(catalog=skill_catalog)

    skill_runtime_policy = (

        SkillRuntimePolicy(

            max_active_skills=3,

            conflict_rules=(),

            workflow_rules=(),

        )

    )



    skill_policy_validator = (

        SkillPolicyValidator(

            policy=skill_runtime_policy

        )

    )

    observation_policy = ToolObservationPolicy(

        max_tokens=args.tool_observation_budget,

    )



    # ============================================================

    # Skill Selection Runtime

    # ============================================================



    skill_selection_runtime = (

        SkillSelectionRuntime(

            catalog=skill_catalog,

            retriever=skill_retriever,

            router=skill_router,

            activation_resolver=activation_resolver,

            policy_validator=skill_policy_validator,

            top_k=3,

        )

    )







    session_manager = SessionManager(Path(args.sessions_dir))



    existed = session_manager.exists(args.session)



    session = session_manager.get_or_create(args.session)



    messages = session.messages

    tool_registry = ToolRegistry()  

    register_standard_tools(

        tool_registry,

        workspace=workspace,

    )

    rag_runtime = None

    if not args.disable_rag:

        if args.embedding_provider == "openai":

            embedding_provider = OpenAICompatibleEmbeddingProvider.from_env()

        else:

            embedding_provider = FakeEmbeddingProvider()

        rag_runtime = await build_rag_runtime(

            workspace=workspace,

            embedding_provider=embedding_provider,

            index_path=Path(args.rag_index),

            migrate_embedding_space=args.migrate_rag_index,

        )

        tool_registry.register(rag_runtime.tool)

    # ============================================================

    # MCP Runtime

    # ============================================================



    mcp_manager: MCPManager | None = None



    if args.enable_mcp_demo:

        # 1. 定位项目根目录与服务器文件

        project_root = Path(__file__).resolve().parents[1]

        mcp_server_file = project_root / "examples" / "mcp_demo_server.py"



        # 2. 连接 MCP 服务器

        mcp_client = await SDKMCPClient.connect_stdio(

            StdioMCPServerConfig(

                name="demo",

                command=sys.executable,

                args=(str(mcp_server_file),),

            )

        )



        # 3. 初始化并启动管理器

        mcp_security_policy = MCPSecurityPolicy(

            allowed_servers=frozenset({"demo"}),

            tool_permissions=(

                MCPToolPermission(

                    server_name="demo",

                    tool_name="lookup_demo_record",

                    risk=MCPToolRisk.READ_ONLY,

                ),

            ),

            resource_servers=frozenset({"demo"}),

            prompt_servers=frozenset({"demo"}),

            max_tool_result_chars=20_000,

        )



        mcp_manager = MCPManager(

            registry=tool_registry,

            clients=(mcp_client,),

            security_policy=mcp_security_policy,

        )



        try:

            await mcp_manager.start()

        except BaseException:

            await mcp_client.close()

            raise     

    context_policy = ContextPolicy(

        max_input_tokens=args.context_budget,

        memory_budget_tokens=args.memory_budget,

        skills_budget_tokens=args.skills_budget,

    )

    runner = AgentRunner(

        provider=provider,

        tool_registry=tool_registry,

        memory_store=memory_store,

        skill_selection_runtime=skill_selection_runtime,

        context_policy=context_policy,

        observation_policy=observation_policy,

        concurrent_tools=True,

    )

    orchestration_runtime = build_orchestration_runtime(

        provider=provider,

        tool_registry=tool_registry,

        workspace=workspace,

        observation_policy=observation_policy,

        context_budget_tokens=args.context_budget,

    )



    agent_loop = AgentLoop(

        runner=runner,

        session_manager=session_manager,

        orchestrator=orchestration_runtime.orchestrator,

    )

    eval_pricing = None
    if args.eval_input_cost_per_million is not None and args.eval_output_cost_per_million is not None:
        eval_pricing = ModelPricing(
            input_per_million=args.eval_input_cost_per_million,
            output_per_million=args.eval_output_cost_per_million,
            currency=args.eval_cost_currency,
        )
    eval_runner = EvalRunner(
        agent_loop=agent_loop,
        trace_reader=JsonlTraceReader(workspace / "orchestration" / "trace.jsonl"),
        pricing=eval_pricing,
        cleanup_sessions=True,
    )

    execution_mode = ExecutionMode(args.execution_mode)

    print("nanobot-rebuild")

    print("runtime : Agent Loop + Tool Calling + RAG")

    print(f"session : {session.session_id}")

    print(f"status  : {'RESTORED' if existed else 'NEW'}")

    print(f"messages: {len(messages)}")

    print(f"provider: {provider.name}")

    print(f"model   : {provider.model}")

    if rag_runtime is not None:

        print(

            "rag     : "

            f"{len(rag_runtime.indexer.index)} chunks, "

            f"{rag_runtime.indexer.embedding_provider.space}"

        )

        if mcp_manager is not None:

            print(

                "mcp     : "

                + ", ".join(

                    mcp_manager

                    .registered_tool_names

                )

            )

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
    print("  /mode           查看当前执行模式")
    print("  /mode MODE      切换 single / orchestrated")
    print("  /eval PATH      运行 JSONL Eval Suite")

    print("  exit            退出程序")

    print("  /memory-forget KEY  删除指定长期记忆")

    last_run_result: (AgentRunResult | None) = None

    try:

        while True:

            raw_input = await asyncio.to_thread(input,"\nYou > ")

            user_message = raw_input.strip()



            if not user_message:

                print("输入不能为空。")

                continue



            if user_message.lower() == "exit":

                print("Bye.")

                return



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

                last_run_result = None

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

                    continue

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

                print(

                    f"Memory consolidation: {changed} changed, "

                    f"{len(candidates)} candidates"

                )

                continue



            if user_message == "/memory-clear":

                memory_store.clear()

                print("长期记忆已清空。")

                continue



            if user_message == "/context":

                if last_run_result is None:

                    print(
                        "\n当前没有可显示的 Single-Agent Runtime Context。"
                        "如果上一轮使用 orchestrated 模式，请通过 Workflow/Trace 查看内部执行。"
                    )

                    continue

                stats = last_run_result.context_stats

                print("\n--- Runtime Context ---")
                print(
                    f"tokens   : "
                    f"{stats.estimated_input_tokens}/{stats.max_input_tokens}"
                )
                print(
                    f"messages : "
                    f"{stats.selected_session_messages}/{stats.total_session_messages}"
                )
                print(
                    f"memory   : "
                    f"{stats.selected_memory_records}/{stats.total_memory_records}"
                )
                print(
                    "skills   : "
                    + (", ".join(stats.active_skills) or "(none)")
                )

                selection = last_run_result.skill_selection

                if selection is not None:

                    print(
                        "route    : "
                        + (
                            ", ".join(
                                selection.route_decision.selected_skills
                            )
                            or "(none)"
                        )
                    )
                    print(
                        f"reason   : "
                        f"{selection.route_decision.reason}"
                    )
                    print(
                        f"confidence: "
                        f"{selection.route_decision.confidence:.3f}"
                    )
                    print("activation:")

                    for activation in selection.activations:

                        print(
                            f"  - {activation.name}: "
                            f"{', '.join(activation.sources)}"
                        )

                print("-----------------------")

                continue

            if user_message.startswith("/memory-forget "):

                key = (

                    user_message

                    .removeprefix("/memory-forget ")

                    .strip()

                )



                if not key:

                    print("用法: /memory-forget KEY")

                    continue



                deleted = memory_store.delete(key)



                if deleted:

                    print(f"已删除长期记忆: {key}")

                else:

                    print(f"未找到长期记忆: {key}")



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

            if user_message == "/mode":

                print(f"当前执行模式: {execution_mode.value}")

                continue



            if user_message.startswith("/mode "):

                raw_mode = user_message.removeprefix("/mode ").strip().lower()

                try:

                    execution_mode = ExecutionMode(raw_mode)

                except ValueError:

                    print("用法: /mode single | /mode orchestrated")

                    continue

                print(f"执行模式已切换为: {execution_mode.value}")

                continue


            if user_message == "/eval":
                print("用法: /eval PATH")
                continue

            if user_message.startswith("/eval "):
                raw_eval_path = user_message.removeprefix("/eval ").strip()

                if not raw_eval_path:
                    print("用法: /eval PATH")
                    continue

                eval_path = Path(raw_eval_path)

                try:
                    cases = load_eval_cases(eval_path)
                    report = await eval_runner.run_suite(cases)
                    report_path = (
                        workspace
                        / "evals"
                        / f"{report.suite_id}.json"
                    )
                    save_eval_report(report, report_path)
                except Exception as exc:
                    print(
                        "\nEval 执行失败: "
                        f"{type(exc).__name__}: {exc}"
                    )
                    continue

                print("\n--- Eval Summary ---")
                print(f"suite  : {report.suite_id}")
                print(f"cases  : {len(cases)}")
                print(f"runs   : {len(report.results)}")

                for summary in report.by_mode:
                    print()
                    print(f"[{summary.mode.value}]")
                    print(f"runs                  : {summary.runs}")
                    print(f"passed                : {summary.passed}")
                    print(f"pass_rate             : {summary.pass_rate:.1%}")
                    print(
                        "execution_success_rate: "
                        f"{summary.execution_success_rate:.1%}"
                    )

                    if summary.workflow_success_rate is not None:
                        print(
                            "workflow_success_rate : "
                            f"{summary.workflow_success_rate:.1%}"
                        )

                    if summary.task_success_rate is not None:
                        print(
                            "task_success_rate     : "
                            f"{summary.task_success_rate:.1%}"
                        )

                    if summary.avg_wall_latency_ms is not None:
                        print(
                            "avg_wall_latency_ms   : "
                            f"{summary.avg_wall_latency_ms:.1f}"
                        )

                    if summary.p50_wall_latency_ms is not None:
                        print(
                            "p50_wall_latency_ms   : "
                            f"{summary.p50_wall_latency_ms:.1f}"
                        )

                    if summary.p95_wall_latency_ms is not None:
                        print(
                            "p95_wall_latency_ms   : "
                            f"{summary.p95_wall_latency_ms:.1f}"
                        )

                    if summary.avg_total_tokens is not None:
                        print(
                            "avg_total_tokens      : "
                            f"{summary.avg_total_tokens:.1f}"
                        )

                    if summary.avg_estimated_cost is not None:
                        print(
                            "avg_estimated_cost    : "
                            f"{summary.avg_estimated_cost:.6f}"
                        )

                print()
                print(f"failures: {report.failure_counts or {}}")
                print(f"report  : {report_path}")
                print("--------------------")
                continue


            try:

                turn_result = await agent_loop.process_user_message(

                    session_id=args.session,

                    content=user_message,

                    mode=execution_mode,

                )

            except Exception as exc:

                print(f"\nAgent 执行失败: {exc}")

                continue


            if turn_result.mode == ExecutionMode.ORCHESTRATED:

                orchestration_result = turn_result.orchestration_result

                if orchestration_result is None:

                    raise RuntimeError(
                        "ORCHESTRATED 模式缺少 orchestration_result"
                    )

                # /context 展示的是 Single-Agent 的 ContextBuilder 统计。
                # Multi-Agent 内部上下文通过 workflow/trace 观察，
                # 因此这里主动清空 last_run_result，避免读到上一轮旧数据。
                last_run_result = None

                print()
                print("--- Workflow ---")
                print(f"id     : {orchestration_result.workflow_id}")
                print(f"trace  : {orchestration_result.trace_id}")
                print(f"status : {orchestration_result.status.value}")
                print(
                    f"tasks  : "
                    f"{len(orchestration_result.task_results)}"
                )
                print("----------------")

                print()
                print(
                    f"Assistant > "
                    f"{orchestration_result.summary}"
                )

            else:

                agent_result = turn_result.run_result

                if agent_result is None:

                    raise RuntimeError(
                        "SINGLE 模式缺少 run_result"
                    )

                last_run_result = agent_result

                if agent_result.tools_used:

                    print()
                    print(
                        "Tools used > "
                        + ", ".join(agent_result.tools_used)
                    )

                stats = agent_result.context_stats

                print(
                    "\nContext > "
                    f"{stats.estimated_input_tokens}/"
                    f"{stats.max_input_tokens} tokens, "
                    f"messages "
                    f"{stats.selected_session_messages}/"
                    f"{stats.total_session_messages}, "
                    f"memory "
                    f"{stats.selected_memory_records}/"
                    f"{stats.total_memory_records}"
                )

                print(
                    f"\nAgent iterations > "
                    f"{agent_result.iterations}"
                )

                print(
                    f"\nAssistant > "
                    f"{agent_result.final_content}"
                )

    finally:



        if mcp_manager is not None:



            await mcp_manager.close()



if __name__ == "__main__":

    asyncio.run(main())
