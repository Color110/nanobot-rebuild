"""将检索结果转换为可验证的结构化证据。"""

from dataclasses import dataclass

from app.rag.document import RetrievedChunk


@dataclass(frozen=True)
class Evidence:
    source: str
    document_id: str
    chunk_id: str
    score: float
    retrieval_method: str
    content: str

    @classmethod
    def from_result(cls, result: RetrievedChunk) -> "Evidence":
        return cls(
            source=result.chunk.source,
            document_id=result.chunk.document_id,
            chunk_id=result.chunk.id,
            score=result.score,
            retrieval_method=result.retrieval_method,
            content=result.chunk.text,
        )


def format_evidence(results: list[RetrievedChunk]) -> str:
    if not results:
        return (
            "No relevant evidence was found. "
            "Do not invent knowledge-base facts or citations."
        )

    sections = [
        "Use only the following evidence for knowledge-base facts. "
        "Cite source and chunk_id. Do not fabricate citations."
    ]
    for index, result in enumerate(results, start=1):
        evidence = Evidence.from_result(result)
        sections.append(
            "\n".join(
                [
                    f"[Evidence {index}]",
                    f"source: {evidence.source}",
                    f"document_id: {evidence.document_id}",
                    f"chunk_id: {evidence.chunk_id}",
                    f"score: {evidence.score:.8f}",
                    f"retrieval_method: {evidence.retrieval_method}",
                    "content:",
                    evidence.content,
                ]
            )
        )
    return "\n\n".join(sections)
