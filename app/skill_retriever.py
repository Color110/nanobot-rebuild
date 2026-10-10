import math
from dataclasses import dataclass

from app.rag.embeddings import EmbeddingProvider, EmbeddingSpace
from app.skill_catalog import SkillCatalog, SkillDescriptor

import math
from collections import Counter

from app.search import SearchTokenizer
from app.skill_catalog import SkillCatalog, SkillDescriptor


@dataclass(frozen=True)
class SkillCandidate:
    skill_name: str
    score: float
    rank: int
    retrieval_method: str = "vector"


@dataclass(frozen=True)
class _SkillVectorEntry:
    descriptor: SkillDescriptor
    vector: tuple[float, ...]

class BM25SkillRetriever:
    def __init__(
        self,
        catalog: SkillCatalog,
        tokenizer: SearchTokenizer,
        *,
        k1: float = 1.5,
        b: float = 0.75,
    ) -> None:
        if k1 <= 0:
            raise ValueError("k1 必须大于 0")

        if not 0.0 <= b <= 1.0:
            raise ValueError("b 必须位于 [0, 1]")

        self.catalog = catalog
        self.tokenizer = tokenizer
        self.k1 = k1
        self.b = b

        self._descriptors: tuple[
            SkillDescriptor, ...
        ] = ()

        self._term_frequencies: list[
            Counter[str]
        ] = []

        self._document_frequencies: Counter[
            str
        ] = Counter()

        self._document_lengths: list[int] = []

        self._average_document_length = 0.0

        self._built = False
    def build_index(self) -> None:
        descriptors = tuple(
            self.catalog.descriptors()
        )

        self._descriptors = descriptors
        self._term_frequencies = []
        self._document_frequencies = Counter()
        self._document_lengths = []

        for descriptor in descriptors:
            terms = self.tokenizer.tokenize(
                descriptor.routing_text()
            )

            frequencies = Counter(terms)

            self._term_frequencies.append(
                frequencies
            )

            self._document_lengths.append(
                len(terms)
            )

            self._document_frequencies.update(
                frequencies.keys()
            )

        if self._document_lengths:
            self._average_document_length = (
                sum(self._document_lengths)
                / len(self._document_lengths)
            )
        else:
            self._average_document_length = 0.0

        self._built = True
    def _score_document(
        self,
        *,
        query_terms: list[str],
        term_frequency: Counter[str],
        document_length: int,
        ) -> float:
        corpus_size = len(
            self._descriptors
        )

        if corpus_size == 0:
            return 0.0

        score = 0.0
        query_term_frequencies = Counter(
            query_terms
        )
        for term in query_term_frequencies:
            tf = term_frequency.get(
                term,
                0,
            )

            if tf == 0:
                continue

            df = self._document_frequencies.get(
                term,
                0,
            )

            idf = math.log(
                1.0
                + (
                    corpus_size
                    - df
                    + 0.5
                )
                / (
                    df
                    + 0.5
                )
            )

            if self._average_document_length > 0:
                length_ratio = (
                    document_length
                    / self._average_document_length
                )
            else:
                length_ratio = 0.0

            denominator = (
                tf
                + self.k1
                * (
                    1.0
                    - self.b
                    + self.b * length_ratio
                )
            )

            score += (
                idf
                * (
                    tf
                    * (self.k1 + 1.0)
                    / denominator
                )
            )

        return score

    async def retrieve(
        self,
        query: str,
        top_k: int = 5,
        ) -> tuple[SkillCandidate, ...]:
        if not query.strip():
            raise ValueError(
                "query 不能为空"
            )

        if top_k <= 0:
            raise ValueError(
                "top_k 必须大于 0"
            )

        if not self._built:
            raise RuntimeError(
                "BM25 Skill index 尚未构建"
            )

        query_terms = (
            self.tokenizer.tokenize(
                query
            )
        )

        if not query_terms:
            return ()

        scored: list[
            tuple[float, str]
        ] = []

        for (
            descriptor,
            term_frequency,
            document_length,
        ) in zip(
            self._descriptors,
            self._term_frequencies,
            self._document_lengths,
            strict=True,
        ):
            score = self._score_document(
                query_terms=query_terms,
                term_frequency=term_frequency,
                document_length=document_length,
            )

            if score > 0:
                scored.append(
                    (
                        score,
                        descriptor.name,
                    )
                )

        ranked = sorted(
            scored,
            key=lambda item: (
                -item[0],
                item[1],
            ),
        )[:top_k]

        return tuple(
            SkillCandidate(
                skill_name=skill_name,
                score=score,
                rank=rank,
                retrieval_method="bm25",
            )
            for rank, (
                score,
                skill_name,
            ) in enumerate(
                ranked,
                start=1,
            )
        )

    async def retrieve(
        self,
        query: str,
        top_k: int = 5,
        ) -> tuple[SkillCandidate, ...]:
        if not query.strip():
            raise ValueError(
                "query 不能为空"
            )

        if top_k <= 0:
            raise ValueError(
                "top_k 必须大于 0"
            )

        if not self._built:
            raise RuntimeError(
                "BM25 Skill index 尚未构建"
            )

        query_terms = (
            self.tokenizer.tokenize(
                query
            )
        )

        if not query_terms:
            return ()

        scored: list[
            tuple[float, str]
        ] = []

        for (
            descriptor,
            term_frequency,
            document_length,
        ) in zip(
            self._descriptors,
            self._term_frequencies,
            self._document_lengths,
            strict=True,
        ):
            score = self._score_document(
                query_terms=query_terms,
                term_frequency=term_frequency,
                document_length=document_length,
            )

            if score > 0:
                scored.append(
                    (
                        score,
                        descriptor.name,
                    )
                )

        ranked = sorted(
            scored,
            key=lambda item: (
                -item[0],
                item[1],
            ),
        )[:top_k]

        return tuple(
            SkillCandidate(
                skill_name=skill_name,
                score=score,
                rank=rank,
                retrieval_method="bm25",
            )
            for rank, (
                score,
                skill_name,
            ) in enumerate(
                ranked,
                start=1,
            )
        )

class SkillVectorIndex:
    def __init__(self, space: EmbeddingSpace) -> None:
        self.space = space
        self._entries: dict[str, _SkillVectorEntry] = {}

    def __len__(self) -> int:
        return len(self._entries)

    def upsert(
        self,
        descriptors: list[SkillDescriptor],
        vectors: list[list[float]],
    ) -> None:
        if len(descriptors) != len(vectors):
            raise ValueError(
                "descriptor 和 vector 数量不一致"
            )

        for descriptor, vector in zip(
            descriptors,
            vectors,
            strict=True,
        ):
            if len(vector) != self.space.dimension:
                raise ValueError(
                    f"Skill '{descriptor.name}' 向量维度错误"
                )

            converted = tuple(float(x) for x in vector)

            if not any(converted):
                raise ValueError(
                    f"Skill '{descriptor.name}' 不能使用零向量"
                )

            self._entries[descriptor.name] = _SkillVectorEntry(
                descriptor=descriptor,
                vector=converted,
            )

    @staticmethod
    def _cosine(
        left: tuple[float, ...],
        right: tuple[float, ...],
    ) -> float:
        dot = sum(
            a * b
            for a, b in zip(left, right, strict=True)
        )

        left_norm = math.sqrt(
            sum(x * x for x in left)
        )

        right_norm = math.sqrt(
            sum(x * x for x in right)
        )

        return dot / (left_norm * right_norm)

    def search(
        self,
        query_vector: list[float],
        top_k: int = 5,
    ) -> tuple[SkillCandidate, ...]:
        if top_k <= 0:
            raise ValueError("top_k 必须大于 0")

        if len(query_vector) != self.space.dimension:
            raise ValueError("Query vector 维度不匹配")

        query = tuple(float(x) for x in query_vector)

        ranked = sorted(
            (
                (
                    self._cosine(query, entry.vector),
                    entry.descriptor.name,
                )
                for entry in self._entries.values()
            ),
            key=lambda item: (-item[0], item[1]),
        )[:top_k]

        return tuple(
            SkillCandidate(
                skill_name=name,
                score=score,
                rank=rank,
            )
            for rank, (score, name) in enumerate(
                ranked,
                start=1,
            )
        )

class SkillRetriever:
    def __init__(
        self,
        catalog: SkillCatalog,
        embedding_provider: EmbeddingProvider,
    ) -> None:
        self.catalog = catalog
        self.embedding_provider = embedding_provider

        self.index = SkillVectorIndex(
            embedding_provider.space
        )

        self._built = False

    async def build_index(self) -> None:
        descriptors = list(
            self.catalog.descriptors()
        )

        if not descriptors:
            self._built = True
            return

        texts = [
            descriptor.routing_text()
            for descriptor in descriptors
        ]

        vectors = await self.embedding_provider.embed_documents(
            texts
        )

        self.index.upsert(
            descriptors,
            vectors,
        )

        self._built = True

    async def retrieve(
        self,
        query: str,
        top_k: int = 5,
    ) -> tuple[SkillCandidate, ...]:
        if not query.strip():
            raise ValueError("query 不能为空")

        if not self._built:
            raise RuntimeError(
                "SkillRetriever index 尚未构建"
            )

        query_vector = (
            await self.embedding_provider.embed_query(query)
        )

        return self.index.search(
            query_vector,
            top_k=top_k,
        )

from collections import defaultdict


def reciprocal_rank_fusion(
    rankings: tuple[
        tuple[SkillCandidate, ...],
        ...
    ],
    *,
    top_k: int,
    rrf_k: int = 60,
) -> tuple[SkillCandidate, ...]:
    if top_k <= 0:
        raise ValueError(
            "top_k 必须大于 0"
        )

    if rrf_k < 0:
        raise ValueError(
            "rrf_k 不能小于 0"
        )

    scores: dict[str, float] = defaultdict(
        float
    )

    for ranking in rankings:
        for candidate in ranking:
            scores[candidate.skill_name] += (
                1.0
                / (
                    rrf_k
                    + candidate.rank
                )
            )

    ranked = sorted(
        scores.items(),
        key=lambda item: (
            -item[1],
            item[0],
        ),
    )[:top_k]

    return tuple(
        SkillCandidate(
            skill_name=skill_name,
            score=score,
            rank=rank,
            retrieval_method="rrf",
        )
        for rank, (
            skill_name,
            score,
        ) in enumerate(
            ranked,
            start=1,
        )
    )

class HybridSkillRetriever:
    def __init__(
        self,
        *,
        vector_retriever: SkillRetriever,
        bm25_retriever: BM25SkillRetriever,
        rrf_k: int = 30,
        candidate_k: int = 10,
    ) -> None:
        if rrf_k < 0:
            raise ValueError(
                "rrf_k 不能小于 0"
            )

        if candidate_k <= 0:
            raise ValueError(
                "candidate_k 必须大于 0"
            )

        self.vector_retriever = (
            vector_retriever
        )

        self.bm25_retriever = (
            bm25_retriever
        )

        self.rrf_k = rrf_k
        self.candidate_k = candidate_k

    async def retrieve(
        self,
        query: str,
        top_k: int = 5,
    ) -> tuple[SkillCandidate, ...]:
        vector_candidates = (
            await self.vector_retriever.retrieve(
                query,
                top_k=self.candidate_k,
            )
        )

        bm25_candidates = (
            await self.bm25_retriever.retrieve(
                query,
                top_k=self.candidate_k,
            )
        )

        return reciprocal_rank_fusion(
            (
                vector_candidates,
                bm25_candidates,
            ),
            top_k=top_k,
            rrf_k=self.rrf_k,
        )