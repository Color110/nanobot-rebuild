from app.rag.bm25 import BM25Index
from app.rag.citation import format_evidence
from app.rag.document import Chunk
from app.rag.embeddings import FakeEmbeddingProvider
from app.rag.retriever import HybridRetriever
from app.rag.vector_index import InMemoryVectorIndex


def make_chunk(chunk_id: str, text: str) -> Chunk:
    return Chunk(
        id=chunk_id,
        document_id=f"doc-{chunk_id}",
        source=f"{chunk_id}.txt",
        text=text,
        index=0,
        token_count=5,
        start_token=0,
        end_token=5,
    )


async def test_hybrid_retrieval_fuses_vector_and_bm25_with_citations() -> None:
    chunks = [
        make_chunk("aurora", "deployment code Aurora-731 internal fact"),
        make_chunk("error", "error code E_CONN_RESET means reconnect"),
        make_chunk("weather", "sunny weather forecast"),
    ]
    provider = FakeEmbeddingProvider(dimension=32)
    vectors = await provider.embed_documents([chunk.text for chunk in chunks])
    vector_index = InMemoryVectorIndex(provider.space)
    vector_index.upsert(chunks, vectors)
    bm25 = BM25Index()
    bm25.rebuild(chunks)
    retriever = HybridRetriever(provider, vector_index, bm25)

    results = await retriever.retrieve("Aurora-731 deployment code", top_k=2)
    evidence = format_evidence(results)

    assert results[0].chunk.id == "aurora"
    assert results[0].retrieval_method.startswith("rrf:")
    assert "source: aurora.txt" in evidence
    assert "chunk_id: aurora" in evidence
    assert retriever.last_trace is not None
    assert retriever.last_trace.vector_candidates == 3


def test_bm25_recalls_exact_error_codes() -> None:
    chunks = [
        make_chunk("exact", "function connect_v2 returned E_CONN_RESET"),
        make_chunk("other", "general connection guidance"),
    ]
    bm25 = BM25Index()
    bm25.rebuild(chunks)

    results = bm25.search("E_CONN_RESET", top_k=1)

    assert results[0].chunk.id == "exact"
