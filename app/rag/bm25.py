"""不依赖外部框架的 BM25 关键词检索。"""

import math
import re
from collections import Counter

from app.rag.document import Chunk, RetrievedChunk


_TERM_PATTERN = re.compile(r"[A-Za-z0-9_./:-]+|[\u3400-\u9fff]")


def tokenize_for_search(text: str) -> list[str]:
    """保留错误码、函数名和型号，并对中文按字建立召回路径。"""

    return [term.lower() for term in _TERM_PATTERN.findall(text)]


class BM25Index:
    def __init__(self, k1: float = 1.5, b: float = 0.75) -> None:
        if k1 <= 0:
            raise ValueError("k1 必须大于 0")
        if not 0 <= b <= 1:
            raise ValueError("b 必须位于 [0, 1]")
        self.k1 = k1
        self.b = b
        self._chunks: list[Chunk] = []
        self._term_frequencies: list[Counter[str]] = []
        self._document_frequencies: Counter[str] = Counter()
        self._average_length = 0.0

    def __len__(self) -> int:
        return len(self._chunks)

    def rebuild(self, chunks: list[Chunk]) -> None:
        self._chunks = list(chunks)
        self._term_frequencies = []
        self._document_frequencies = Counter()

        total_length = 0
        for chunk in self._chunks:
            terms = tokenize_for_search(chunk.text)
            frequencies = Counter(terms)
            self._term_frequencies.append(frequencies)
            self._document_frequencies.update(frequencies.keys())
            total_length += len(terms)

        self._average_length = (
            total_length / len(self._chunks) if self._chunks else 0.0
        )

    def search(self, query: str, top_k: int = 5) -> list[RetrievedChunk]:
        if top_k <= 0:
            raise ValueError("top_k 必须大于 0")
        query_terms = tokenize_for_search(query)
        if not query_terms or not self._chunks:
            return []

        corpus_size = len(self._chunks)
        scored: list[tuple[float, Chunk]] = []
        for chunk, frequencies in zip(
            self._chunks, self._term_frequencies, strict=True
        ):
            document_length = sum(frequencies.values())
            score = 0.0
            for term in query_terms:
                frequency = frequencies.get(term, 0)
                if frequency == 0:
                    continue
                document_frequency = self._document_frequencies[term]
                inverse_document_frequency = math.log(
                    1
                    + (corpus_size - document_frequency + 0.5)
                    / (document_frequency + 0.5)
                )
                length_ratio = (
                    document_length / self._average_length
                    if self._average_length
                    else 0.0
                )
                denominator = frequency + self.k1 * (
                    1 - self.b + self.b * length_ratio
                )
                score += inverse_document_frequency * (
                    frequency * (self.k1 + 1) / denominator
                )
            if score > 0:
                scored.append((score, chunk))

        ranked = sorted(scored, key=lambda item: (-item[0], item[1].id))[:top_k]
        return [
            RetrievedChunk(
                chunk=chunk,
                score=score,
                retrieval_method="bm25",
                rank=rank,
            )
            for rank, (score, chunk) in enumerate(ranked, start=1)
        ]
