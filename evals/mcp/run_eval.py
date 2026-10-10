from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
import statistics
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.providers import OpenAICompatibleProvider


SYSTEM_PROMPT = """你是一个带 MCP 工具的 Agent。
当用户需要外部数据或外部动作时，从给定工具中选择最匹配的工具。
如果问题只需要通用知识回答，不要调用工具。
不要因为工具名称相似就跨服务器误选；严格依据用户指定的数据源。
高风险工具是否最终允许执行由 Runtime Security Policy 决定；你只负责产生正确的工具意图。
"""


@dataclass
class EvalRecord:
    trace_id: str
    case_id: str
    repetition: int
    category: str
    expected_decision: str
    expected_tool: str | None
    actual_tools: list[str]
    tool_call_ids: list[str]
    selection_pass: bool
    arguments_pass: bool
    forbidden_tool_pass: bool
    case_pass: bool
    latency_ms: float
    content: str
    error: str | None = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate MCP tool routing")
    parser.add_argument("--cases", default="evals/mcp/routing_cases.jsonl")
    parser.add_argument("--tool-catalog", default="evals/mcp/tool_catalog.json")
    parser.add_argument("--repeat", type=int, default=3)
    parser.add_argument("--results-dir", default="evals/mcp/results")
    parser.add_argument("--baseline", default=None)
    parser.add_argument("--validate-only", action="store_true")
    return parser.parse_args()


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        row = json.loads(line)
        row["_line"] = line_no
        rows.append(row)
    return rows


def load_cases(path: Path) -> list[dict[str, Any]]:
    cases = load_jsonl(path)
    if not cases:
        raise ValueError("MCP Eval cases 不能为空")
    required = {
        "id", "layer", "category", "prompt", "expected_decision",
        "expected_tool", "expected_arguments", "forbidden_tools",
    }
    ids: set[str] = set()
    for case in cases:
        missing = required - set(case)
        if missing:
            raise ValueError(
                f"{path}:{case['_line']} 缺少字段: {sorted(missing)}"
            )
        if case["id"] in ids:
            raise ValueError(f"重复 case id: {case['id']}")
        ids.add(case["id"])
        if case["layer"] != "routing":
            raise ValueError(
                f"run_eval.py 只运行 routing cases，收到 layer={case['layer']}: {case['id']}"
            )
    return cases


def load_tools(path: Path) -> list[dict[str, Any]]:
    catalog = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(catalog, list) or not catalog:
        raise ValueError("tool_catalog.json 必须是非空数组")
    names = [item["name"] for item in catalog]
    if len(names) != len(set(names)):
        raise ValueError("Tool catalog 中存在重复 name")
    return [
        {
            "type": "function",
            "function": {
                "name": item["name"],
                "description": item["description"],
                "parameters": item["parameters"],
            },
        }
        for item in catalog
    ]


def args_subset_match(expected: dict[str, Any], actual: dict[str, Any]) -> bool:
    for key, value in expected.items():
        if key not in actual or actual[key] != value:
            return False
    return True


def score_case(case: dict[str, Any], response) -> tuple[bool, bool, bool, list[str], list[str]]:
    actual_tools = [call.name for call in response.tool_calls]
    tool_call_ids = [call.id for call in response.tool_calls]

    if case["expected_decision"] == "no_tool":
        selection_pass = len(actual_tools) == 0
        arguments_pass = True
    else:
        selection_pass = (
            len(actual_tools) == 1
            and actual_tools[0] == case["expected_tool"]
        )
        arguments_pass = (
            selection_pass
            and args_subset_match(
                dict(case["expected_arguments"]),
                dict(response.tool_calls[0].arguments),
            )
        )

    forbidden = set(case["forbidden_tools"])
    forbidden_tool_pass = not any(name in forbidden for name in actual_tools)
    return (
        selection_pass,
        arguments_pass,
        forbidden_tool_pass,
        actual_tools,
        tool_call_ids,
    )


async def run_one(provider, tools, case, repetition: int) -> EvalRecord:
    trace_id = uuid.uuid4().hex
    started = time.perf_counter()
    try:
        response = await provider.complete(
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": case["prompt"]},
            ],
            tools=tools,
        )
        latency_ms = (time.perf_counter() - started) * 1000
        (
            selection_pass,
            arguments_pass,
            forbidden_tool_pass,
            actual_tools,
            tool_call_ids,
        ) = score_case(case, response)
        case_pass = selection_pass and arguments_pass and forbidden_tool_pass
        return EvalRecord(
            trace_id=trace_id,
            case_id=case["id"],
            repetition=repetition,
            category=case["category"],
            expected_decision=case["expected_decision"],
            expected_tool=case["expected_tool"],
            actual_tools=actual_tools,
            tool_call_ids=tool_call_ids,
            selection_pass=selection_pass,
            arguments_pass=arguments_pass,
            forbidden_tool_pass=forbidden_tool_pass,
            case_pass=case_pass,
            latency_ms=latency_ms,
            content=response.content,
        )
    except Exception as exc:
        return EvalRecord(
            trace_id=trace_id,
            case_id=case["id"],
            repetition=repetition,
            category=case["category"],
            expected_decision=case["expected_decision"],
            expected_tool=case["expected_tool"],
            actual_tools=[],
            tool_call_ids=[],
            selection_pass=False,
            arguments_pass=False,
            forbidden_tool_pass=False,
            case_pass=False,
            latency_ms=(time.perf_counter() - started) * 1000,
            content="",
            error=f"{type(exc).__name__}: {exc}",
        )


def mean_bool(records: list[EvalRecord], field: str) -> float:
    if not records:
        return 0.0
    return statistics.fmean(
        1.0 if getattr(record, field) else 0.0
        for record in records
    )


def percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, round((len(ordered) - 1) * q)))
    return ordered[index]


def summarize(records: list[EvalRecord]) -> dict[str, float]:
    tool_records = [
        r for r in records
        if r.expected_decision != "no_tool"
    ]
    no_tool_records = [
        r for r in records
        if r.expected_decision == "no_tool"
    ]
    latencies = [r.latency_ms for r in records]
    return {
        "case_pass_rate": mean_bool(records, "case_pass"),
        "tool_selection_accuracy": mean_bool(records, "selection_pass"),
        "argument_accuracy_on_tool_cases": mean_bool(tool_records, "arguments_pass"),
        "no_tool_accuracy": mean_bool(no_tool_records, "selection_pass"),
        "forbidden_tool_pass_rate": mean_bool(records, "forbidden_tool_pass"),
        "avg_latency_ms": statistics.fmean(latencies) if latencies else 0.0,
        "p50_latency_ms": percentile(latencies, 0.50),
        "p95_latency_ms": percentile(latencies, 0.95),
    }


def category_summary(records: list[EvalRecord]) -> dict[str, dict[str, float]]:
    categories = sorted({r.category for r in records})
    result = {}
    for category in categories:
        rows = [r for r in records if r.category == category]
        result[category] = {
            "count": float(len(rows)),
            "case_pass_rate": mean_bool(rows, "case_pass"),
            "selection_accuracy": mean_bool(rows, "selection_pass"),
        }
    return result


def compare_baseline(summary: dict[str, float], path: Path) -> dict[str, float]:
    baseline = json.loads(path.read_text(encoding="utf-8"))
    old = baseline["summary"]
    return {
        key: float(summary[key]) - float(old[key])
        for key in summary
        if key in old
    }


def write_csv(path: Path, records: list[EvalRecord]) -> None:
    rows = [asdict(r) for r in records]
    if not rows:
        return
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        for row in rows:
            row["actual_tools"] = json.dumps(row["actual_tools"], ensure_ascii=False)
            row["tool_call_ids"] = json.dumps(row["tool_call_ids"], ensure_ascii=False)
            writer.writerow(row)


async def main() -> None:
    args = parse_args()
    cases_path = Path(args.cases).resolve()
    tools_path = Path(args.tool_catalog).resolve()
    results_dir = Path(args.results_dir).resolve()
    results_dir.mkdir(parents=True, exist_ok=True)

    cases = load_cases(cases_path)
    tools = load_tools(tools_path)

    print("=== MCP Eval Dataset ===")
    print(f"cases : {len(cases)}")
    print(f"tools : {len(tools)}")
    print(f"categories: {len(set(c['category'] for c in cases))}")

    if args.validate_only:
        print("validation: PASS")
        return

    if not os.getenv("LLM_API_KEY") or not os.getenv("LLM_MODEL"):
        raise RuntimeError(
            "真实评测需要 LLM_API_KEY 和 LLM_MODEL；"
            "可先使用 --validate-only 验证数据集。"
        )

    provider = OpenAICompatibleProvider.from_env()
    records: list[EvalRecord] = []

    for case in cases:
        for repetition in range(1, args.repeat + 1):
            record = await run_one(provider, tools, case, repetition)
            records.append(record)
            print(
                f"[{case['id']} #{repetition}] "
                f"pass={record.case_pass} "
                f"tools={record.actual_tools} "
                f"latency={record.latency_ms:.0f}ms"
            )

    summary = summarize(records)
    by_category = category_summary(records)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    payload: dict[str, Any] = {
        "timestamp": timestamp,
        "provider": provider.name,
        "model": provider.model,
        "repeat": args.repeat,
        "case_count": len(cases),
        "summary": summary,
        "by_category": by_category,
        "records": [asdict(r) for r in records],
    }

    if args.baseline:
        payload["baseline_delta"] = compare_baseline(
            summary,
            Path(args.baseline).resolve(),
        )

    json_path = results_dir / f"mcp-eval-{timestamp}.json"
    csv_path = results_dir / f"mcp-eval-{timestamp}.csv"
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    write_csv(csv_path, records)

    print("\n=== Summary ===")
    for key, value in summary.items():
        if key.endswith("accuracy") or key.endswith("rate"):
            print(f"{key}: {value:.2%}")
        else:
            print(f"{key}: {value:.2f}")
    print(f"json: {json_path}")
    print(f"csv : {csv_path}")


if __name__ == "__main__":
    asyncio.run(main())
