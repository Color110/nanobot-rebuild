from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


from app.providers.openai_compatible import (
    OpenAICompatibleProvider,
)

from app.rag.embeddings.openai_compatible import (
    OpenAICompatibleEmbeddingProvider,
)

from app.search import (
    SearchTokenizer,
)

from app.skill_activation import (
    ActivationResolver,
)

from app.skill_catalog import (
    SkillCatalog,
)

from app.skill_policy import (
    SkillPolicyValidator,
    SkillRuntimePolicy,
)

from app.skill_retriever import (
    BM25SkillRetriever,
    HybridSkillRetriever,
    SkillRetriever,
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

from app.skills import (
    SkillLoader,
)


# ============================================================
# Eval Case
# ============================================================


@dataclass(frozen=True)
class EvalCase:
    case_id: str
    query: str
    expected_skills: tuple[str, ...]
    difficulty: str
    case_type: str


@dataclass
class CaseResult:
    case_id: str
    case_type: str
    difficulty: str
    query: str

    expected_skills: list[str]

    retrieval_candidates: list[str]
    router_selected: list[str]
    activations: list[str]
    snapshots: list[str]

    top1_correct: bool | None
    candidate_hit: bool | None

    router_exact: bool
    runtime_exact: bool
    system_correct: bool

    error: str | None = None


# ============================================================
# Dataset
# ============================================================


def load_positive_cases(
    path: Path,
) -> list[EvalCase]:
    cases: list[EvalCase] = []

    with path.open(
        "r",
        encoding="utf-8",
    ) as file:
        for line_number, line in enumerate(
            file,
            start=1,
        ):
            line = line.strip()

            if not line:
                continue

            raw = json.loads(line)

            try:
                case_id = str(raw["id"])
                query = str(raw["query"])
                expected_skill = str(
                    raw["expected_skill"]
                )
            except KeyError as exc:
                raise ValueError(
                    f"{path}:{line_number} "
                    f"缺少字段 {exc}"
                ) from exc

            difficulty = str(
                raw.get(
                    "difficulty",
                    "unknown",
                )
            )

            cases.append(
                EvalCase(
                    case_id=case_id,
                    query=query,
                    expected_skills=(
                        expected_skill,
                    ),
                    difficulty=difficulty,
                    case_type="positive",
                )
            )

    return cases


def load_negative_cases(
    path: Path,
) -> list[EvalCase]:
    cases: list[EvalCase] = []

    with path.open(
        "r",
        encoding="utf-8",
    ) as file:
        for line_number, line in enumerate(
            file,
            start=1,
        ):
            line = line.strip()

            if not line:
                continue

            raw = json.loads(line)

            try:
                case_id = str(raw["id"])
                query = str(raw["query"])
            except KeyError as exc:
                raise ValueError(
                    f"{path}:{line_number} "
                    f"缺少字段 {exc}"
                ) from exc

            expected = raw.get(
                "expected_skills",
                [],
            )

            if expected != []:
                raise ValueError(
                    f"{path}:{line_number} "
                    "No-Skill Case 的 "
                    "expected_skills 必须为空"
                )

            cases.append(
                EvalCase(
                    case_id=case_id,
                    query=query,
                    expected_skills=(),
                    difficulty="no-skill",
                    case_type="negative",
                )
            )

    return cases


# ============================================================
# Build Skill Runtime
# ============================================================


async def build_skill_runtime(
    *,
    workspace: Path,
    top_k: int,
) -> tuple[
    SkillSelectionRuntime,
    set[str],
]:
    # --------------------------------------------------------
    # SkillLoader
    # --------------------------------------------------------

    loader = SkillLoader(
        workspace=workspace
    )

    skills = loader.list_skills()

    if not skills:
        raise RuntimeError(
            f"没有加载到 Skill: {workspace}"
        )

    print(
        f"[Init] loaded skills: "
        f"{len(skills)}"
    )

    # --------------------------------------------------------
    # Catalog
    # --------------------------------------------------------

    catalog = SkillCatalog(
        skills
    )

    always_skill_names = {
        skill.name
        for skill in skills
        if (
            skill.enabled
            and skill.always
        )
    }

    # --------------------------------------------------------
    # Real Embedding Provider
    # --------------------------------------------------------

    embedding_provider = (
        OpenAICompatibleEmbeddingProvider
        .from_env()
    )

    # --------------------------------------------------------
    # Vector Retriever
    # --------------------------------------------------------

    vector_retriever = SkillRetriever(
        catalog=catalog,
        embedding_provider=(
            embedding_provider
        ),
    )

    print(
        "[Init] building "
        "Skill Vector Index ..."
    )

    await vector_retriever.build_index()

    # --------------------------------------------------------
    # BM25 Retriever
    # --------------------------------------------------------

    tokenizer = SearchTokenizer()

    bm25_retriever = (
        BM25SkillRetriever(
            catalog=catalog,
            tokenizer=tokenizer,
        )
    )

    bm25_retriever.build_index()

    # --------------------------------------------------------
    # RRF Hybrid Retriever
    # --------------------------------------------------------

    hybrid_retriever = (
        HybridSkillRetriever(
            vector_retriever=(
                vector_retriever
            ),
            bm25_retriever=(
                bm25_retriever
            ),
            rrf_k=60,
            candidate_k=len(skills),
        )
    )

    # --------------------------------------------------------
    # Real LLM Router
    # --------------------------------------------------------

    llm_provider = (
        OpenAICompatibleProvider
        .from_env()
    )

    router_model = (
        LLMProviderSkillRouterAdapter(
            provider=llm_provider
        )
    )

    router = SkillRouter(
        model=router_model
    )

    # --------------------------------------------------------
    # Activation
    # --------------------------------------------------------

    activation_resolver = (
        ActivationResolver(
            catalog=catalog
        )
    )

    # --------------------------------------------------------
    # Runtime Policy
    # --------------------------------------------------------

    runtime_policy = (
        SkillRuntimePolicy(
            max_active_skills=3,
            conflict_rules=(),
            workflow_rules=(),
        )
    )

    policy_validator = (
        SkillPolicyValidator(
            policy=runtime_policy
        )
    )

    # --------------------------------------------------------
    # Final Selection Runtime
    # --------------------------------------------------------

    runtime = SkillSelectionRuntime(
        catalog=catalog,
        retriever=hybrid_retriever,
        router=router,
        activation_resolver=(
            activation_resolver
        ),
        policy_validator=(
            policy_validator
        ),
        top_k=top_k,
    )

    return (
        runtime,
        always_skill_names,
    )


# ============================================================
# Single Case
# ============================================================


async def evaluate_case(
    *,
    runtime: SkillSelectionRuntime,
    case: EvalCase,
    always_skill_names: set[str],
) -> CaseResult:
    expected_semantic = set(
        case.expected_skills
    )

    # always Skill 不属于 Router 的预测目标，
    # 但属于最终 Runtime Activation。
    expected_runtime = (
        expected_semantic
        | always_skill_names
    )

    try:
        result = await runtime.select(
            user_query=case.query
        )

        retrieval_names = [
            candidate.skill_name
            for candidate
            in result.retrieval_candidates
        ]

        router_names = list(
            result
            .route_decision
            .selected_skills
        )

        activation_names = [
            activation.name
            for activation
            in result.activations
        ]

        snapshot_names = [
            snapshot.name
            for snapshot
            in result.snapshots
        ]

        router_set = set(
            router_names
        )

        snapshot_set = set(
            snapshot_names
        )

        # ----------------------------------------------------
        # Positive Case
        # ----------------------------------------------------

        if case.case_type == "positive":
            expected_skill = (
                case.expected_skills[0]
            )

            top1_correct = bool(
                retrieval_names
                and (
                    retrieval_names[0]
                    == expected_skill
                )
            )

            candidate_hit = (
                expected_skill
                in retrieval_names
            )

            # 当前数据集是单 Skill GT，
            # 所以选 expected + 一个额外 Skill
            # 也算错误。
            router_exact = (
                router_set
                == expected_semantic
            )

            runtime_exact = (
                snapshot_set
                == expected_runtime
            )

            system_correct = (
                router_exact
                and runtime_exact
            )

        # ----------------------------------------------------
        # No-Skill Case
        # ----------------------------------------------------

        else:
            top1_correct = None
            candidate_hit = None

            # No-Skill 测的是 semantic router
            # 是否能够拒绝所有候选。
            router_exact = (
                len(router_set) == 0
            )

            # 如果系统配置了 always Skill，
            # 它仍然可以进入 Snapshot。
            runtime_exact = (
                snapshot_set
                == always_skill_names
            )

            system_correct = (
                router_exact
                and runtime_exact
            )

        return CaseResult(
            case_id=case.case_id,
            case_type=case.case_type,
            difficulty=case.difficulty,
            query=case.query,
            expected_skills=list(
                case.expected_skills
            ),
            retrieval_candidates=(
                retrieval_names
            ),
            router_selected=router_names,
            activations=activation_names,
            snapshots=snapshot_names,
            top1_correct=top1_correct,
            candidate_hit=candidate_hit,
            router_exact=router_exact,
            runtime_exact=runtime_exact,
            system_correct=system_correct,
        )

    except Exception as exc:
        return CaseResult(
            case_id=case.case_id,
            case_type=case.case_type,
            difficulty=case.difficulty,
            query=case.query,
            expected_skills=list(
                case.expected_skills
            ),
            retrieval_candidates=[],
            router_selected=[],
            activations=[],
            snapshots=[],
            top1_correct=False
            if case.case_type == "positive"
            else None,
            candidate_hit=False
            if case.case_type == "positive"
            else None,
            router_exact=False,
            runtime_exact=False,
            system_correct=False,
            error=(
                f"{type(exc).__name__}: "
                f"{exc}"
            ),
        )


# ============================================================
# Metrics
# ============================================================


def safe_ratio(
    numerator: int,
    denominator: int,
) -> float:
    if denominator == 0:
        return 0.0

    return (
        numerator
        / denominator
    )


def compute_metrics(
    results: list[CaseResult],
) -> dict[str, Any]:
    positive = [
        result
        for result in results
        if result.case_type
        == "positive"
    ]

    negative = [
        result
        for result in results
        if result.case_type
        == "negative"
    ]

    # --------------------------------------------------------
    # Retriever
    # --------------------------------------------------------

    top1_correct = sum(
        result.top1_correct is True
        for result in positive
    )

    candidate_hits = sum(
        result.candidate_hit is True
        for result in positive
    )

    # --------------------------------------------------------
    # Router
    # --------------------------------------------------------

    conditional_router_correct = sum(
        (
            result.candidate_hit is True
            and result.router_exact
        )
        for result in positive
    )

    # --------------------------------------------------------
    # Full Selection Runtime
    # --------------------------------------------------------

    e2e_correct = sum(
        result.system_correct
        for result in positive
    )

    # --------------------------------------------------------
    # No Skill
    # --------------------------------------------------------

    no_skill_correct = sum(
        result.system_correct
        for result in negative
    )

    false_activations = (
        len(negative)
        - no_skill_correct
    )

    # --------------------------------------------------------
    # Errors
    # --------------------------------------------------------

    errors = sum(
        result.error is not None
        for result in results
    )

    metrics: dict[str, Any] = {
        "positive_cases": len(
            positive
        ),
        "negative_cases": len(
            negative
        ),
        "total_cases": len(
            results
        ),

        "top1_correct": top1_correct,
        "top1_baseline_accuracy": (
            safe_ratio(
                top1_correct,
                len(positive),
            )
        ),

        "candidate_hits": (
            candidate_hits
        ),
        "candidate_recall_at_3": (
            safe_ratio(
                candidate_hits,
                len(positive),
            )
        ),

        "conditional_router_correct": (
            conditional_router_correct
        ),
        "conditional_router_accuracy": (
            safe_ratio(
                conditional_router_correct,
                candidate_hits,
            )
        ),

        "e2e_correct": e2e_correct,
        "e2e_skill_selection_accuracy": (
            safe_ratio(
                e2e_correct,
                len(positive),
            )
        ),

        "no_skill_correct": (
            no_skill_correct
        ),
        "no_skill_accuracy": (
            safe_ratio(
                no_skill_correct,
                len(negative),
            )
        ),

        "false_activations": (
            false_activations
        ),
        "false_activation_rate": (
            safe_ratio(
                false_activations,
                len(negative),
            )
        ),

        "errors": errors,
    }

    # --------------------------------------------------------
    # Difficulty Breakdown
    # --------------------------------------------------------

    difficulty_metrics: dict[
        str,
        Any,
    ] = {}

    difficulties = sorted(
        {
            result.difficulty
            for result in positive
        }
    )

    for difficulty in difficulties:
        subset = [
            result
            for result in positive
            if result.difficulty
            == difficulty
        ]

        difficulty_metrics[
            difficulty
        ] = {
            "count": len(subset),
            "candidate_recall_at_3": (
                safe_ratio(
                    sum(
                        result.candidate_hit
                        is True
                        for result
                        in subset
                    ),
                    len(subset),
                )
            ),
            "e2e_accuracy": (
                safe_ratio(
                    sum(
                        result.system_correct
                        for result
                        in subset
                    ),
                    len(subset),
                )
            ),
        }

    metrics[
        "by_difficulty"
    ] = difficulty_metrics

    return metrics


# ============================================================
# Regression
# ============================================================


def load_baseline(
    path: Path,
) -> dict[str, bool]:
    raw = json.loads(
        path.read_text(
            encoding="utf-8"
        )
    )

    case_results = raw.get(
        "cases",
        []
    )

    return {
        str(case["case_id"]): bool(
            case["system_correct"]
        )
        for case in case_results
    }


def compute_regression(
    *,
    results: list[CaseResult],
    baseline_path: Path,
) -> dict[str, Any]:
    baseline = load_baseline(
        baseline_path
    )

    counts = {
        "FIXED": 0,
        "REGRESSED": 0,
        "UNCHANGED_PASS": 0,
        "UNCHANGED_FAIL": 0,
        "NEW_CASE": 0,
    }

    details: list[
        dict[str, Any]
    ] = []

    for result in results:
        old = baseline.get(
            result.case_id
        )

        new = result.system_correct

        if old is None:
            label = "NEW_CASE"

        elif (
            old is False
            and new is True
        ):
            label = "FIXED"

        elif (
            old is True
            and new is False
        ):
            label = "REGRESSED"

        elif (
            old is True
            and new is True
        ):
            label = "UNCHANGED_PASS"

        else:
            label = "UNCHANGED_FAIL"

        counts[label] += 1

        if label in {
            "FIXED",
            "REGRESSED",
        }:
            details.append(
                {
                    "case_id": (
                        result.case_id
                    ),
                    "classification": (
                        label
                    ),
                    "query": result.query,
                    "expected_skills": (
                        result
                        .expected_skills
                    ),
                    "router_selected": (
                        result
                        .router_selected
                    ),
                    "snapshots": (
                        result.snapshots
                    ),
                }
            )

    counts["net_gain"] = (
        counts["FIXED"]
        - counts["REGRESSED"]
    )

    return {
        "counts": counts,
        "changed_cases": details,
    }


# ============================================================
# Output
# ============================================================


def print_metrics(
    metrics: dict[str, Any],
) -> None:
    def pct(
        value: float,
    ) -> str:
        return (
            f"{value * 100:.2f}%"
        )

    print()
    print(
        "========================================"
    )
    print(
        "       Skill System Final Eval"
    )
    print(
        "========================================"
    )

    print(
        f"Positive Cases : "
        f"{metrics['positive_cases']}"
    )

    print(
        f"No-Skill Cases : "
        f"{metrics['negative_cases']}"
    )

    print()
    print(
        "--- Retrieval ---"
    )

    print(
        "Top1 Baseline Accuracy : "
        + pct(
            metrics[
                "top1_baseline_accuracy"
            ]
        )
    )

    print(
        "Candidate Recall@3     : "
        + pct(
            metrics[
                "candidate_recall_at_3"
            ]
        )
    )

    print()
    print(
        "--- Router ---"
    )

    print(
        "Conditional Router Acc : "
        + pct(
            metrics[
                "conditional_router_accuracy"
            ]
        )
    )

    print()
    print(
        "--- End-to-End Selection ---"
    )

    print(
        "E2E Skill Accuracy     : "
        + pct(
            metrics[
                "e2e_skill_selection_accuracy"
            ]
        )
    )

    print()
    print(
        "--- No Skill ---"
    )

    print(
        "No-Skill Accuracy      : "
        + pct(
            metrics[
                "no_skill_accuracy"
            ]
        )
    )

    print(
        "False Activation Rate  : "
        + pct(
            metrics[
                "false_activation_rate"
            ]
        )
    )

    print()
    print(
        f"Runtime / Router Errors: "
        f"{metrics['errors']}"
    )

    print()
    print(
        "--- Difficulty ---"
    )

    for difficulty, values in (
        metrics[
            "by_difficulty"
        ].items()
    ):
        print(
            f"{difficulty:<8} "
            f"N={values['count']:<4} "
            "R@3="
            + pct(
                values[
                    "candidate_recall_at_3"
                ]
            )
            + "  E2E="
            + pct(
                values[
                    "e2e_accuracy"
                ]
            )
        )

    print(
        "========================================"
    )


# ============================================================
# Main
# ============================================================


async def async_main(
    args: argparse.Namespace,
) -> None:
    positive_path = Path(
        args.positive
    )

    negative_path = Path(
        args.negative
    )

    workspace = Path(
        args.workspace
    )

    output_path = Path(
        args.output
    )

    if not positive_path.exists():
        raise FileNotFoundError(
            positive_path
        )

    if not negative_path.exists():
        raise FileNotFoundError(
            negative_path
        )

    positive_cases = (
        load_positive_cases(
            positive_path
        )
    )

    negative_cases = (
        load_negative_cases(
            negative_path
        )
    )

    cases = [
        *positive_cases,
        *negative_cases,
    ]

    if args.max_cases is not None:
        positive_limit = min(
            args.max_cases,
            len(positive_cases),
        )

        cases = [
            *positive_cases[
                :positive_limit
            ],
            *negative_cases,
        ]

    runtime, always_skill_names = (
        await build_skill_runtime(
            workspace=workspace,
            top_k=args.top_k,
        )
    )

    print(
        f"[Eval] total cases: "
        f"{len(cases)}"
    )

    print(
        f"[Eval] always skills: "
        f"{sorted(always_skill_names)}"
    )

    results: list[
        CaseResult
    ] = []

    for index, case in enumerate(
        cases,
        start=1,
    ):
        result = await evaluate_case(
            runtime=runtime,
            case=case,
            always_skill_names=(
                always_skill_names
            ),
        )

        results.append(
            result
        )

        status = (
            "PASS"
            if result.system_correct
            else "FAIL"
        )

        print(
            f"[{index:03d}/{len(cases):03d}] "
            f"{status:<4} "
            f"{case.case_id}"
        )

        if result.error:
            print(
                "    error: "
                f"{result.error}"
            )

    metrics = compute_metrics(
        results
    )

    print_metrics(
        metrics
    )

    regression = None

    if args.baseline:
        baseline_path = Path(
            args.baseline
        )

        if not baseline_path.exists():
            raise FileNotFoundError(
                baseline_path
            )

        regression = (
            compute_regression(
                results=results,
                baseline_path=(
                    baseline_path
                ),
            )
        )

        counts = regression[
            "counts"
        ]

        print()
        print(
            "--- Regression ---"
        )

        print(
            f"FIXED          : "
            f"{counts['FIXED']}"
        )

        print(
            f"REGRESSED      : "
            f"{counts['REGRESSED']}"
        )

        print(
            f"UNCHANGED PASS : "
            f"{counts['UNCHANGED_PASS']}"
        )

        print(
            f"UNCHANGED FAIL : "
            f"{counts['UNCHANGED_FAIL']}"
        )

        print(
            f"NET GAIN       : "
            f"{counts['net_gain']:+d}"
        )

    output = {
        "config": {
            "workspace": str(
                workspace
            ),
            "positive_dataset": str(
                positive_path
            ),
            "negative_dataset": str(
                negative_path
            ),
            "top_k": args.top_k,
        },
        "metrics": metrics,
        "regression": regression,
        "cases": [
            asdict(result)
            for result in results
        ],
    }

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    output_path.write_text(
        json.dumps(
            output,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print()
    print(
        f"[Saved] {output_path}"
    )


def build_arg_parser(
) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Skill Selection Runtime "
            "final evaluation"
        )
    )

    parser.add_argument(
        "--workspace",
        default="workspace",
    )

    parser.add_argument(
        "--positive",
        default=(
            "evals/skills/"
            "retrieval_cases.jsonl"
        ),
    )

    parser.add_argument(
        "--negative",
        default=(
            "evals/skills/"
            "no_skill_cases_v1.jsonl"
        ),
    )

    parser.add_argument(
        "--top-k",
        type=int,
        default=3,
    )

    parser.add_argument(
        "--output",
        default=(
            "evals/skills/results/"
            "skill_system_eval_current.json"
        ),
    )

    parser.add_argument(
        "--baseline",
        default=None,
    )

    # 仅用于先做小规模运行检查。
    # 正式结果不要使用它。
    parser.add_argument(
        "--max-cases",
        type=int,
        default=None,
    )

    return parser


def main() -> None:
    parser = build_arg_parser()

    args = parser.parse_args()

    asyncio.run(
        async_main(args)
    )


if __name__ == "__main__":
    main()