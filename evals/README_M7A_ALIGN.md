# M7-A Runtime Integration

Add:
- `app/execution_mode.py`
- `app/orchestration/bootstrap.py`

Replace:
- `app/agent_loop.py`

Export from `app/orchestration/__init__.py`:

```python
from .bootstrap import OrchestrationRuntime, build_orchestration_runtime
```

and add both names to `__all__`.

In `app/main.py`:

1. Add imports:

```python
from app.execution_mode import ExecutionMode
from app.orchestration import build_orchestration_runtime
```

2. Add CLI argument:

```python
parser.add_argument(
    "--execution-mode",
    choices=[mode.value for mode in ExecutionMode],
    default=ExecutionMode.SINGLE.value,
    help="本轮默认执行模式：single 或 orchestrated",
)
```

3. Build `observation_policy` once, then use it for both runtimes:

```python
observation_policy = ToolObservationPolicy(
    max_tokens=args.tool_observation_budget,
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

execution_mode = ExecutionMode(args.execution_mode)
```

4. Optional interactive commands:

```python
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
```

5. Call AgentLoop with the selected mode:

```python
turn_result = await agent_loop.process_user_message(
    session_id=args.session,
    content=user_message,
    mode=execution_mode,
)
```

6. Print by mode:

```python
if turn_result.mode == ExecutionMode.SINGLE:
    agent_result = turn_result.run_result
    assert agent_result is not None
    last_run_result = agent_result
    # keep your existing single-agent tool/context printing
else:
    orchestration_result = turn_result.orchestration_result
    assert orchestration_result is not None
    last_run_result = None

    print("\n--- Workflow ---")
    print(f"id     : {orchestration_result.workflow_id}")
    print(f"trace  : {orchestration_result.trace_id}")
    print(f"status : {orchestration_result.status.value}")
    print(f"tasks  : {len(orchestration_result.task_results)}")
    print("----------------")
    print(f"\nAssistant > {orchestration_result.summary}")
```

Do not add `auto` routing yet. M7-B will first add Eval and then evaluate an automatic router.
