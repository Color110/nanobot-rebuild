# MCP M7 Evaluation Bundle

这是面向 Agent / AI 应用开发面试的 MCP M7（Observability + Evaluation）评测包。

## 数据规模

总计 **200 条** Case：

- Routing / Tool Selection：120
- Security：50
- Host Primitive（Resources / Prompts）：30

当前类别分布：

```json
{
  "filesystem_read": 18,
  "filesystem_search": 18,
  "github_search_code": 16,
  "github_get_issue": 12,
  "database_query_customer": 16,
  "database_search_orders": 12,
  "mail_search": 8,
  "cross_server_disambiguation": 10,
  "no_tool": 10,
  "high_risk_delete": 10,
  "high_risk_create_issue": 8,
  "high_risk_update_customer": 8,
  "high_risk_send_email": 10,
  "prompt_injection": 8,
  "unlisted_capability": 6,
  "resource_read": 15,
  "prompt_get": 15
}
```

## 文件

- `evals/mcp/tool_catalog.json`：用于真实 LLM Tool Selection Eval 的 MCP Tool Catalog
- `evals/mcp/routing_cases.jsonl`：120 条真实 LLM 路由与参数提取 Case
- `evals/mcp/security_cases.jsonl`：50 条高风险、副作用、Prompt Injection、Allowlist Case
- `evals/mcp/host_primitive_cases.jsonl`：30 条 Resource / Prompt Host 控制 Case
- `evals/mcp/run_eval.py`：真实 LLM Routing Eval Runner
- `evals/mcp/manifest.json`：数据集统计与哈希
- `tests/test_mcp_eval_dataset.py`：数据集规模与覆盖度回归测试

## M7 推荐指标

Routing：

- Tool Selection Accuracy
- Argument Accuracy
- No-Tool Accuracy
- Forbidden Tool Pass Rate
- Case Pass Rate
- P50 / P95 Latency

Security：

- Confirmation Required 命中率
- Prompt Injection Dangerous-Tool Block Rate
- Unlisted Capability Block Rate

Runtime Observability：

每条执行记录至少保留：

- `trace_id`
- `case_id`
- `tool_call_ids`
- `expected_tool`
- `actual_tools`
- `latency_ms`
- `error`

不要把 Secret、完整隐私内容或大段 Tool Result 无条件写入日志。

## 使用

先把整个 `evals/mcp/` 和 `tests/test_mcp_eval_dataset.py` 放进项目根目录对应位置。

### 1. 验证数据集

```bash
python evals/mcp/run_eval.py --validate-only
pytest -q tests/test_mcp_eval_dataset.py
```

预期数据：

- routing = 120
- security = 50
- host primitive = 30
- total = 200

### 2. 真实模型 Routing Eval

```bash
export LLM_API_KEY="..."
export LLM_MODEL="..."
# OpenAI-compatible 服务可选：
export LLM_BASE_URL="..."

python evals/mcp/run_eval.py --repeat 3
```

正式做 baseline 建议 `--repeat 5`：

```bash
python evals/mcp/run_eval.py --repeat 5
```

这会产生 120 × 5 = 600 次路由样本，已经足够作为当前项目的稳定回归基线。

### 3. Baseline 对比

第一次稳定结果记为 baseline：

```bash
python evals/mcp/run_eval.py --repeat 5
```

后续修改 Tool description、MCP naming、Provider、System Prompt 后：

```bash
python evals/mcp/run_eval.py \
  --repeat 5 \
  --baseline evals/mcp/results/mcp-eval-<OLD_TIMESTAMP>.json
```

## 为什么没有把 200 条全部交给真实 LLM

`security_cases.jsonl` 和 `host_primitive_cases.jsonl` 很多 Case 的正确性由 Runtime Policy / Host 控制，而不是由模型“选得准不准”决定。

因此：

- 120 条 Routing：真实 LLM 概率性评测
- 50 条 Security：结合 M6 的确定性 Runtime 测试与后续安全 Eval
- 30 条 Resources / Prompts：Host-controlled 行为验证

这样不会把 Tool Selection、Security Policy、Host Primitive 三种不同控制语义混成一个指标。

## M7 完成标准

1. 数据集校验测试通过。
2. Routing `--validate-only` 通过。
3. 使用固定模型跑至少 3 次；建立 baseline 时推荐 5 次。
4. 结果至少报告 Tool Selection、Argument Accuracy、No-Tool Accuracy、Forbidden Tool Pass Rate、Case Pass Rate、P95 Latency。
5. M5/M6 的 reliability/security pytest 全部回归通过。
6. 修改 Tool Schema / description / Security Policy 后，用同一数据集重跑并比较 baseline。
