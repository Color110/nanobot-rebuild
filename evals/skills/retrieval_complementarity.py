from dataclasses import dataclass

from app.skill_retriever import SkillCandidate

import argparse
import asyncio
from pathlib import Path

from app.rag.embeddings import OpenAICompatibleEmbeddingProvider
from app.search import SearchTokenizer
from app.skill_catalog import SkillCatalog
from app.skill_retriever import SkillRetriever, BM25SkillRetriever
from app.skills import SkillLoader

from evals.skills.run_retrieval_eval import load_cases


@dataclass(frozen=True)
class ComplementarityCaseResult:
    case_id: str
    query: str
    expected_skill: str

    vector_candidates: tuple[SkillCandidate, ...]
    bm25_candidates: tuple[SkillCandidate, ...]

    vector_hit: bool
    bm25_hit: bool

def contains_expected(
    candidates: tuple[SkillCandidate, ...],
    expected_skill: str,
    k: int,
) -> bool:
    return any(
        candidate.skill_name == expected_skill
        and candidate.rank <= k
        for candidate in candidates
    )

# def contains_expected(
#     candidates: tuple[SkillCandidate, ...],
#     expected_skill: str,
# ) -> bool:
#     return any(
#         candidate.skill_name == expected_skill
#         for candidate in candidates
#     )

async def evaluate_case(
    *,
    case,
    vector_retriever,
    bm25_retriever,
    top_k: int,
) -> ComplementarityCaseResult:
    vector_candidates = (
        await vector_retriever.retrieve(
            case.query,
            top_k=top_k,
        )
    )

    bm25_candidates = (
        await bm25_retriever.retrieve(
            case.query,
            top_k=top_k,
        )
    )

    vector_hit = contains_expected(
        vector_candidates,
        case.expected_skill,
        top_k,
    )

    bm25_hit = contains_expected(
        bm25_candidates,
        case.expected_skill,
        top_k,
    )

    return ComplementarityCaseResult(
        case_id=case.id,
        query=case.query,
        expected_skill=case.expected_skill,
        vector_candidates=vector_candidates,
        bm25_candidates=bm25_candidates,
        vector_hit=vector_hit,
        bm25_hit=bm25_hit,
    )

@dataclass(frozen=True)
class ComplementaritySummary:
    total: int

    both_hit: int
    vector_only: int
    bm25_only: int
    neither: int

    vector_recall: float
    bm25_recall: float
    oracle_recall: float
    bm25_rescue_rate: float

def summarize_complementarity(
    results: list[ComplementarityCaseResult],
) -> ComplementaritySummary:
    total = len(results)

    both_hit = 0
    vector_only = 0
    bm25_only = 0
    neither = 0

    for result in results:
        if result.vector_hit and result.bm25_hit:
            both_hit += 1

        elif result.vector_hit:
            vector_only += 1

        elif result.bm25_hit:
            bm25_only += 1

        else:
            neither += 1

    if total == 0:
        return ComplementaritySummary(
            total=0,
            both_hit=0,
            vector_only=0,
            bm25_only=0,
            neither=0,
            vector_recall=0.0,
            bm25_recall=0.0,
            oracle_recall=0.0,
            bm25_rescue_rate=0.0,
        )

    vector_hits = (
        both_hit
        + vector_only
    )

    bm25_hits = (
        both_hit
        + bm25_only
    )

    vector_misses = (
        bm25_only
        + neither
    )

    vector_recall = (
        vector_hits / total
    )

    bm25_recall = (
        bm25_hits / total
    )

    oracle_recall = (
        both_hit
        + vector_only
        + bm25_only
    ) / total

    if vector_misses:
        bm25_rescue_rate = (
            bm25_only
            / vector_misses
        )
    else:
        bm25_rescue_rate = 0.0

    return ComplementaritySummary(
        total=total,
        both_hit=both_hit,
        vector_only=vector_only,
        bm25_only=bm25_only,
        neither=neither,
        vector_recall=vector_recall,
        bm25_recall=bm25_recall,
        oracle_recall=oracle_recall,
        bm25_rescue_rate=bm25_rescue_rate,
    )


def print_summary(
    summary: ComplementaritySummary,
    top_k: int,
) -> None:
    print(
        f"\n=== Complementarity @{top_k} ==="
    )

    print(
        f"Total:        {summary.total}"
    )

    print(
        f"Both hit:     {summary.both_hit}"
    )

    print(
        f"Vector only:  {summary.vector_only}"
    )

    print(
        f"BM25 only:    {summary.bm25_only}"
    )

    print(
        f"Neither:      {summary.neither}"
    )

    print()

    print(
        f"Vector R@{top_k}: "
        f"{summary.vector_recall:.2%}"
    )

    print(
        f"BM25 R@{top_k}:   "
        f"{summary.bm25_recall:.2%}"
    )

    print(
        f"Oracle R@{top_k}: "
        f"{summary.oracle_recall:.2%}"
    )

    print(
        "BM25 rescue rate: "
        f"{summary.bm25_rescue_rate:.2%}"
    )

def print_bm25_only_cases(
    results: list[ComplementarityCaseResult],
) -> None:
    print(
        "\n=== BM25-only Hits ==="
    )

    for result in results:
        if (
            result.vector_hit
            or not result.bm25_hit
        ):
            continue

        print()
        print(
            f"[{result.case_id}] "
            f"{result.query}"
        )

        print(
            "expected:",
            result.expected_skill,
        )

        print("Vector:")
        for candidate in (
            result.vector_candidates
        ):
            print(
                f"  {candidate.rank}. "
                f"{candidate.skill_name:<22} "
                f"{candidate.score:.4f}"
            )

        print("BM25:")
        for candidate in (
            result.bm25_candidates
        ):
            print(
                f"  {candidate.rank}. "
                f"{candidate.skill_name:<22} "
                f"{candidate.score:.4f}"
            )

def print_vector_only_cases(
    results: list[ComplementarityCaseResult],
) -> None:
    print(
        "\n=== Vector-only Hits ==="
    )

    for result in results:
        if (
            not result.vector_hit
            or result.bm25_hit
        ):
            continue

        print(
            f"[{result.case_id}] "
            f"{result.query}"
        )




async def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--cases",
        type=Path,
        default=Path(
            "evals/skills/retrieval_cases.jsonl"
        ),
    )

    parser.add_argument(
        "--top-k",
        type=int,
        default=3,
    )

    args = parser.parse_args()

    # 1. 加载 Skill
    loader = SkillLoader(
        Path("workspace")
    )

    catalog = SkillCatalog(
        loader.list_skills()
    )

    # 2. Vector Retriever
    embedding_provider = (
        OpenAICompatibleEmbeddingProvider.from_env()
    )

    vector_retriever = SkillRetriever(
        catalog=catalog,
        embedding_provider=embedding_provider,
    )

    await vector_retriever.build_index()

    # 3. BM25 Retriever
    tokenizer = SearchTokenizer()

    bm25_retriever = BM25SkillRetriever(
        catalog=catalog,
        tokenizer=tokenizer,
    )

    bm25_retriever.build_index()

    # 4. 加载同一份 Eval Set
    cases = load_cases(
        args.cases
    )

    results = []

    try:
        for case in cases:
            result = await evaluate_case(
                case=case,
                vector_retriever=vector_retriever,
                bm25_retriever=bm25_retriever,
                top_k=args.top_k,
            )

            results.append(result)

        # 5. 汇总
        summary = summarize_complementarity(
            results
        )

        print_summary(
            summary,
            top_k=args.top_k,
        )

        # 6. 打印最有价值的 Failure
        print_bm25_only_cases(
            results
        )

        print_vector_only_cases(
            results
        )

    finally:
        await embedding_provider.close()


if __name__ == "__main__":
    asyncio.run(main())




