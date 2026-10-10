# M6 对齐说明

基于当前 M5：Durable TaskStore + Scheduler + Recovery。

## 新增文件

- `app/orchestration/tracing.py`
- `app/orchestration/reducer.py`
- `app/orchestration/orchestrator.py`
- `examples/m6_orchestrator_smoke.py`

## 替换/合并文件

- `app/orchestration/scheduler.py`
- `app/orchestration/executor.py`
- `app/orchestration/__init__.py`
- `app/agent.py`

## M6 形成的主链

`User Goal -> WorkflowOrchestrator -> LLMPlanner -> TaskPlanValidator -> TaskScheduler -> SubAgentExecutor -> WorkflowRunResult -> DeterministicResultReducer -> OrchestrationResult`

Trace 使用同一个 `trace_id` 贯穿 Orchestrator、Scheduler 和 SubAgentExecutor。恢复 `resume(workflow_id)` 默认生成新的 trace_id，但继续使用原 durable workflow_id。

## 运行冒烟测试

```bash
PYTHONPATH=. python examples/m6_orchestrator_smoke.py
```

预期：

```text
M6 ORCHESTRATOR SMOKE PASSED
...
status: SUCCEEDED
output_task_ids: ('write_report',)
...
```

## 已验证兼容性

- M6 Orchestrator smoke：通过
- 原 M2/M3 orchestration tests：10 passed
- M5 durable smoke 三个恢复场景：全部通过
- SubAgentExecutor Tool trace：`tool_call_id` 可正确进入 `TOOL_COMPLETED` TraceEvent
