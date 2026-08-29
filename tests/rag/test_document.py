from math import inf

import pytest
from pydantic import ValidationError

from app.rag.document import Chunk, Document, RetrievedChunk


def test_rag_models_preserve_citation_identity() -> None:
    document = Document(
        id="doc-1",
        source="policies/company.txt",
        text="内部代号是 Aurora-731。",
        metadata={"department": "engineering"},
    )
    chunk = Chunk(
        id="chunk-1",
        document_id=document.id,
        source=document.source,
        text=document.text,
        index=0,
        token_count=8,
        start_token=0,
        end_token=8,
    )
    result = RetrievedChunk(
        chunk=chunk,
        score=0.9,
        retrieval_method="vector",
        rank=1,
    )

    assert result.chunk.document_id == "doc-1"
    assert result.chunk.id == "chunk-1"
    assert result.chunk.source == "policies/company.txt"


def test_chunk_rejects_inconsistent_token_range() -> None:
    with pytest.raises(ValidationError, match="token_count"):
        Chunk(
            id="chunk-1",
            document_id="doc-1",
            source="file.txt",
            text="content",
            index=0,
            token_count=2,
            start_token=0,
            end_token=3,
        )


def test_retrieved_chunk_rejects_non_finite_score() -> None:
    chunk = Chunk(
        id="chunk-1",
        document_id="doc-1",
        source="file.txt",
        text="content",
        index=0,
        token_count=1,
        start_token=0,
        end_token=1,
    )

    with pytest.raises(ValidationError, match="有限"):
        RetrievedChunk(
            chunk=chunk,
            score=inf,
            retrieval_method="bm25",
            rank=1,
        )
