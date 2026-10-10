import argparse
import asyncio
import json
from dataclasses import dataclass
from pathlib import Path

from app.rag.embeddings import (
    FakeEmbeddingProvider,
    OpenAICompatibleEmbeddingProvider,
)
from app.skill_catalog import SkillCatalog
from app.skill_retriever import SkillCandidate, SkillRetriever
from app.skills import SkillLoader


@dataclass(frozen=True)
class RetrievalEvalCase:
    id: str
    query: str
    expected_skill: str
    difficulty: str


@dataclass(frozen=True)
class RetrievalEvalResult:
    case: RetrievalEvalCase
    candidates: tuple[SkillCandidate, ...]
    expected_rank: int | None


def load_cases(path: Path) -> list[RetrievalEvalCase]:
    cases: list[RetrievalEvalCase] = []

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
                case = RetrievalEvalCase(
                    id=raw["id"],
                    query=raw["query"],
                    expected_skill=raw["expected_skill"],
                    difficulty=raw.get(
                        "difficulty",
                        "unknown",
                    ),
                )
            except KeyError as exc:
                raise ValueError(
                    f"第 {line_number} 行缺少字段: {exc}"
                ) from exc

            cases.append(case)

    return cases
def find_expected_rank(
    candidates: tuple[SkillCandidate, ...],
    expected_skill: str,
) -> int | None:
    for candidate in candidates:
        if candidate.skill_name == expected_skill:
            return candidate.rank

    return None
def recall_at_k(
    results: list[RetrievalEvalResult],
    k: int,
    ) -> float:
    if not results:
        return 0.0

    hits = sum(
        1
        for result in results
        if result.expected_rank is not None
        and result.expected_rank <= k
    )

    return hits / len(results)
def mean_reciprocal_rank(
    results: list[RetrievalEvalResult],
) -> float:
    if not results:
        return 0.0

    reciprocal_sum = sum(
        0.0
        if result.expected_rank is None
        else 1.0 / result.expected_rank
        for result in results
    )

    return reciprocal_sum / len(results)

async def evaluate(
    retriever: SkillRetriever,
    cases: list[RetrievalEvalCase],
    top_k: int,
) -> list[RetrievalEvalResult]:
    results: list[RetrievalEvalResult] = []

    for case in cases:
        candidates = await retriever.retrieve(
            case.query,
            top_k=top_k,
        )

        rank = find_expected_rank(
            candidates,
            case.expected_skill,
        )

        results.append(
            RetrievalEvalResult(
                case=case,
                candidates=candidates,
                expected_rank=rank,
            )
        )

    return results

def print_metrics(
    results: list[RetrievalEvalResult],
) -> None:
    print()
    print("=== Skill Retrieval Eval ===")

    for k in (1, 3, 5):
        value = recall_at_k(
            results,
            k,
        )

        print(
            f"Recall@{k}: {value:.2%}"
        )

    mrr = mean_reciprocal_rank(results)

    print(
        f"MRR:      {mrr:.4f}"
    )

def print_failures(
    results: list[RetrievalEvalResult],
    k: int = 3,
    ) -> None:
    failures = [
        result
        for result in results
        if result.expected_rank is None
        or result.expected_rank > k
    ]

    print()
    print(
        f"=== Recall@{k} Failures ==="
    )

    if not failures:
        print("None")
        return

    for result in failures:
        print()
        print(
            f"[{result.case.id}] "
            f"{result.case.query}"
        )

        print(
            "expected:",
            result.case.expected_skill,
        )

        for candidate in result.candidates:
            print(
                f"  {candidate.rank}. "
                f"{candidate.skill_name:<20} "
                f"{candidate.score:.4f}"
            )

def group_by_difficulty(
    results: list[RetrievalEvalResult],
) -> dict[str, list[RetrievalEvalResult]]:
    groups: dict[
        str,
        list[RetrievalEvalResult],
    ] = {}

    for result in results:
        groups.setdefault(
            result.case.difficulty,
            [],
        ).append(result)

    return groups
def print_difficulty_metrics(
    results: list[RetrievalEvalResult],
) -> None:
    print()
    print("=== By Difficulty ===")

    groups = group_by_difficulty(results)

    for difficulty, group in groups.items():
        r1 = recall_at_k(group, 1)
        r3 = recall_at_k(group, 3)
        mrr = mean_reciprocal_rank(group)

        print(
            f"{difficulty:<10} "
            f"R@1={r1:.2%} "
            f"R@3={r3:.2%} "
            f"MRR={mrr:.4f}"
        )
def build_embedding_provider(name: str):
    if name == "fake":
        return FakeEmbeddingProvider(
            dimension=64
        )

    if name == "real":
        return OpenAICompatibleEmbeddingProvider.from_env()

    raise ValueError(
        f"unknown provider: {name}"
    )

from app.search import SearchTokenizer
from app.skill_retriever import (
    SkillRetriever,
    BM25SkillRetriever,
    HybridSkillRetriever
)

async def build_retriever(
    *,
    retriever_type: str,
    catalog: SkillCatalog,
    embedding_provider,
):
    if retriever_type == "vector":
        retriever = SkillRetriever(
            catalog=catalog,
            embedding_provider=embedding_provider,
        )

        await retriever.build_index()

        return retriever

    if retriever_type == "bm25":
        tokenizer = SearchTokenizer()

        retriever = BM25SkillRetriever(
            catalog=catalog,
            tokenizer=tokenizer,
        )

        retriever.build_index()

        return retriever

    raise ValueError(
        f"unknown retriever: "
        f"{retriever_type}"
    )


async def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--cases",
        default="/mnt/nanobot-rebuild/evals/skills/retrieval_cases.jsonl",
    )

    parser.add_argument(
        "--top-k",
        type=int,
        default=5,
    )
    parser.add_argument(
        "--provider",
        choices=("fake", "real"),
        default="real",
    )

    parser.add_argument(
        "--retriever",
        choices=(
            "vector",
            "bm25",
            "hybrid",
        ),
        default="hybrid",
    )
    args = parser.parse_args()

    loader = SkillLoader(
        Path("workspace")
    )

    catalog = SkillCatalog(
        loader.list_skills()
    )

    # provider = FakeEmbeddingProvider(
    #     dimension=64
    # )
    provider = build_embedding_provider(
        args.provider
    )

    # retriever = SkillRetriever(
    #     catalog=catalog,
    #     embedding_provider=provider,
    # )
    # retriever = await build_retriever(
    #     retriever_type=args.retriever,
    #     catalog=catalog,
    #     embedding_provider=provider,
    # )
    # if isinstance(retriever, BM25SkillRetriever):
    #     retriever.build_index()       # 同步，不加 await
    # else:
    #     await retriever.build_index() # 异步，加 await
    if args.retriever == "hybrid":
        vector = SkillRetriever(
            catalog=catalog,
            embedding_provider=provider,
        )

        await vector.build_index()

        bm25 = BM25SkillRetriever(
            catalog=catalog,
            tokenizer=SearchTokenizer(),
        )

        bm25.build_index()

        retriever = HybridSkillRetriever(
            vector_retriever=vector,
            bm25_retriever=bm25,
            rrf_k=60,
            candidate_k=16,
        )
    cases = load_cases(
        Path(args.cases)
    )

    results = await evaluate(
        retriever,
        cases,
        top_k=args.top_k,
    )

    print_metrics(results)
    print_difficulty_metrics(results)
    print_failures(
        results,
        k=3,
    )



if __name__ == "__main__":
    asyncio.run(main())
