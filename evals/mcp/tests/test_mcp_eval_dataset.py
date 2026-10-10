from __future__ import annotations

import json
from collections import Counter
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
EVAL_ROOT = PROJECT_ROOT / "evals" / "mcp"


def load_jsonl(name: str) -> list[dict]:
    path = EVAL_ROOT / name
    rows = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    return rows


def test_mcp_eval_dataset_shape_and_size():
    routing = load_jsonl("routing_cases.jsonl")
    security = load_jsonl("security_cases.jsonl")
    host = load_jsonl("host_primitive_cases.jsonl")

    assert len(routing) == 120
    assert len(security) == 50
    assert len(host) == 30
    assert len(routing) + len(security) + len(host) == 200

    all_cases = routing + security + host
    ids = [case["id"] for case in all_cases]
    assert len(ids) == len(set(ids))


def test_routing_dataset_has_sufficient_coverage():
    routing = load_jsonl("routing_cases.jsonl")
    counts = Counter(case["category"] for case in routing)

    assert counts["filesystem_read"] >= 15
    assert counts["filesystem_search"] >= 15
    assert counts["github_search_code"] >= 15
    assert counts["github_get_issue"] >= 10
    assert counts["database_query_customer"] >= 15
    assert counts["database_search_orders"] >= 10
    assert counts["mail_search"] >= 8
    assert counts["cross_server_disambiguation"] >= 10
    assert counts["no_tool"] >= 10


def test_security_dataset_has_high_risk_and_injection_cases():
    security = load_jsonl("security_cases.jsonl")
    counts = Counter(case["category"] for case in security)

    assert counts["high_risk_delete"] >= 10
    assert counts["high_risk_send_email"] >= 10
    assert counts["prompt_injection"] >= 8
    assert counts["unlisted_capability"] >= 6

    confirmation = [
        case for case in security
        if case["expected_decision"] == "confirmation_required"
    ]
    assert confirmation
    assert all(
        case["expected_error_type"] == "MCP_CONFIRMATION_REQUIRED"
        for case in confirmation
    )


def test_host_primitive_dataset_covers_resources_and_prompts():
    host = load_jsonl("host_primitive_cases.jsonl")
    counts = Counter(case["category"] for case in host)

    assert counts["resource_read"] == 15
    assert counts["prompt_get"] == 15
