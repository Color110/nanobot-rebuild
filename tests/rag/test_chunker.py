import pytest

from app.rag.chunker import TokenChunker
from app.rag.document import Document


def test_token_chunker_uses_token_windows_and_overlap() -> None:
    document = Document(
        id="doc-1",
        source="facts.txt",
        text="one two three four five six seven eight nine ten",
        metadata={"format": "text"},
    )
    chunker = TokenChunker(chunk_size_tokens=4, overlap_tokens=1)

    chunks = chunker.chunk(document)

    assert len(chunks) > 1
    assert all(chunk.token_count <= 4 for chunk in chunks)
    assert all(chunk.document_id == document.id for chunk in chunks)
    assert all(chunk.source == document.source for chunk in chunks)
    assert all(chunk.metadata == document.metadata for chunk in chunks)
    assert chunks[1].start_token == chunks[0].end_token - 1
    assert chunks[-1].end_token == len(chunker._encoding.encode(document.text))


def test_token_chunker_produces_stable_chunk_ids() -> None:
    document = Document(id="doc-1", source="facts.txt", text="alpha beta gamma")
    chunker = TokenChunker(chunk_size_tokens=2, overlap_tokens=0)

    assert chunker.chunk(document) == chunker.chunk(document)


@pytest.mark.parametrize(
    ("chunk_size", "overlap", "message"),
    [
        (0, 0, "大于 0"),
        (10, -1, "不能小于 0"),
        (10, 10, "必须小于"),
        (10, 11, "必须小于"),
    ],
)
def test_token_chunker_validates_configuration(
    chunk_size: int,
    overlap: int,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        TokenChunker(chunk_size_tokens=chunk_size, overlap_tokens=overlap)
