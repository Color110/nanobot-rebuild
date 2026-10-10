import asyncio

from app.orchestration import (
    AgentSpec,
    LLMPlanner,
    OrchestrationPolicy,
    TaskPlanValidator,
)
from app.providers import (
    FakeProvider,
    ProviderResponse,
    ToolCallRequest,
)


async def main() -> None:
    # ============================================================
    # 1. Runtime-owned AgentSpec
    #
    # 注意：
    # 这些能力是 Runtime 预先配置好的，
    # Planner 只能从这里选择，不能自己创造 Agent 或授予 Tool。
    # ============================================================

    agent_specs = {
        "researcher": AgentSpec(
            agent_type="researcher",
            system_prompt=(
                "你负责资料检索、事实核验和证据整理，"
                "优先获取可靠、可追溯的信息。"
            ),
            allowed_tools=frozenset(
                {
                    "search_web",
                }
            ),
        ),
        "writer": AgentSpec(
            agent_type="writer",
            system_prompt=(
                "你负责基于已经提供的研究结果整理和撰写报告，"
                "不得凭空补充没有证据支持的事实。"
            ),
            allowed_tools=frozenset(),
        ),
    }

    # ============================================================
    # 2. Runtime-owned OrchestrationPolicy
    #
    # Planner 可以看到部分限制，
    # 但真正的硬校验仍然由 TaskPlanValidator 完成。
    # ============================================================

    policy = OrchestrationPolicy(
        max_tasks=8,
        max_depth=4,
        max_concurrency=4,
        workflow_timeout_seconds=300.0,
        max_total_llm_calls=32,
        max_total_tokens=100_000,
    )

    # ============================================================
    # 3. FakeProvider 模拟 LLM Planner 输出
    #
    # 这里不访问真实模型。
    #
    # 我们假设模型收到：
    # “调查目标公司的融资情况并写成报告”
    #
    # 然后通过 submit_task_plan 提交下面这个 DAG：
    #
    # research
    #    ↓
    # write
    # ============================================================

    provider = FakeProvider(
        responses=[
            ProviderResponse(
                content="",
                tool_calls=[
                    ToolCallRequest(
                        id="call_plan_1",
                        name="submit_task_plan",
                        arguments={
                            "plan_version": "1",
                            "tasks": [
                                {
                                    "task_id": "research",
                                    "objective": (
                                        "调查目标公司的融资情况，"
                                        "整理关键融资轮次、金额和投资方信息。"
                                    ),
                                    "agent_type": "researcher",
                                    "dependencies": [],
                                    "requested_tools": [
                                        "search_web",
                                    ],
                                    "required": True,
                                    "input_data": {
                                        "company": "Demo Company",
                                    },
                                },
                                {
                                    "task_id": "write",
                                    "objective": (
                                        "根据 research 任务的调查结果，"
                                        "生成一份简洁的融资情况报告。"
                                    ),
                                    "agent_type": "writer",
                                    "dependencies": [
                                        "research",
                                    ],
                                    "requested_tools": [],
                                    "required": True,
                                    "input_data": {},
                                },
                            ],
                        },
                    )
                ],
            )
        ]
    )

    # ============================================================
    # 4. 创建 LLMPlanner
    # ============================================================

    planner = LLMPlanner(
        provider=provider,
        agent_specs=agent_specs,
        policy=policy,
    )

    # ============================================================
    # 5. User Goal → LLMPlanner → TaskPlan
    #
    # 这里得到的 TaskPlan 仍然属于“不可信 Planner 输出”。
    # 它还不能直接执行。
    # ============================================================

    plan = await planner.plan(
        user_goal="调查目标公司的融资情况，并根据结果写一份简短报告。",
        context={
            "language": "zh-CN",
            "report_style": "concise",
        },
    )

    print("=" * 70)
    print("STEP 1: LLMPlanner 生成 TaskPlan")
    print("=" * 70)

    print(f"plan_version: {plan.plan_version}")
    print(f"task_count: {len(plan.tasks)}")

    for task in plan.tasks:
        print()
        print(f"task_id: {task.task_id}")
        print(f"objective: {task.objective}")
        print(f"agent_type: {task.agent_type}")
        print(f"dependencies: {task.dependencies}")
        print(f"requested_tools: {task.requested_tools}")
        print(f"required: {task.required}")
        print(f"input_data: {task.input_data}")

    # ============================================================
    # 6. 检查 Planner 是否真的使用了 submit_task_plan Schema
    #
    # FakeProvider 会保存 complete() 收到的 messages / tools。
    # 所以这里可以确认：
    #
    # LLMPlanner 确实向 Provider 暴露了 submit_task_plan。
    # ============================================================

    print()
    print("=" * 70)
    print("STEP 2: 检查 Planner 发给 Provider 的结构化输出 Tool")
    print("=" * 70)

    assert len(provider.calls) == 1

    provider_call = provider.calls[0]

    sent_tools = provider_call["tools"]
    assert sent_tools is not None
    assert len(sent_tools) == 1

    tool_name = sent_tools[0]["function"]["name"]

    print(f"tool_name: {tool_name}")

    assert tool_name == "submit_task_plan"

    # ============================================================
    # 7. 查看 Planner 构造出的 Prompt
    #
    # 这里主要确认 Agent Catalog 和 User Goal 已经传给模型。
    # ============================================================

    sent_messages = provider_call["messages"]

    print()
    print("=" * 70)
    print("STEP 3: 检查 Planner Prompt")
    print("=" * 70)

    print(f"message_count: {len(sent_messages)}")
    print()

    for index, message in enumerate(sent_messages, start=1):
        print(f"[Message {index}] role={message['role']}")
        print(message["content"])
        print("-" * 70)

    # ============================================================
    # 8. TaskPlan → TaskPlanValidator
    #
    # 这是 M3 和 M1 真正接起来的位置。
    #
    # Planner 只负责 proposal。
    # Runtime Validator 才负责：
    #
    # - agent_type 校验
    # - Tool 授权检查
    # - Dependency 检查
    # - DAG 环检查
    # - Depth 检查
    # - RuntimeTask 创建
    # ============================================================

    validator = TaskPlanValidator(
        agent_specs=agent_specs,
        policy=policy,
    )

    graph = validator.validate_and_resolve(
        plan,
        workflow_id="workflow-m3-smoke-001",
    )

    print()
    print("=" * 70)
    print("STEP 4: TaskPlanValidator 生成 ResolvedTaskGraph")
    print("=" * 70)

    print(f"workflow_id: {graph.workflow_id}")
    print(f"topological_order: {graph.topological_order}")
    print(f"depth_by_task: {graph.depth_by_task}")

    # ============================================================
    # 9. 查看 RuntimeTask
    #
    # 这里非常关键：
    #
    # Planner 输出的是 requested_tools。
    #
    # Validator 之后形成的 RuntimeTask
    # 才真正拥有 granted_tools 和 Runtime Budget。
    # ============================================================

    print()
    print("=" * 70)
    print("STEP 5: 查看 Runtime 授权后的 RuntimeTask")
    print("=" * 70)

    for task in graph.tasks:
        print()
        print(f"task_id: {task.task_id}")
        print(f"agent_type: {task.agent_type}")
        print(f"dependencies: {task.dependencies}")
        print(f"granted_tools: {task.granted_tools}")
        print(f"status: {task.status}")
        print(f"attempt: {task.attempt}")
        print(f"budget: {task.budget}")

    # ============================================================
    # 10. 最小机制断言
    # ============================================================

    assert [task.task_id for task in plan.tasks] == [
        "research",
        "write",
    ]

    assert graph.topological_order == (
        "research",
        "write",
    )

    runtime_tasks = graph.by_id

    assert runtime_tasks["research"].granted_tools == (
        "search_web",
    )

    assert runtime_tasks["write"].granted_tools == ()

    assert runtime_tasks["write"].dependencies == (
        "research",
    )

    # ============================================================
    # 11. Smoke Test 通过
    # ============================================================

    print()
    print("=" * 70)
    print("M3 SMOKE TEST PASSED")
    print("=" * 70)

    print(
        "User Goal "
        "→ LLMPlanner "
        "→ submit_task_plan "
        "→ TaskPlan "
        "→ TaskPlanValidator "
        "→ ResolvedTaskGraph"
    )


if __name__ == "__main__":
    asyncio.run(main())