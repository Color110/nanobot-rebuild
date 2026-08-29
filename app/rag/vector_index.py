"""可观察、可持久化的 brute-force 向量索引。"""

import asyncio
import json
import math
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from app.rag.document import Chunk, RetrievedChunk
from app.rag.embeddings import EmbeddingProvider, EmbeddingSpace


INDEX_SCHEMA_VERSION = 1


class VectorIndexError(RuntimeError):
    """向量索引数据或操作不满足契约。"""


class IndexMigrationRequiredError(VectorIndexError):
    """持久化索引的 Embedding Space 与当前 Provider 不兼容。"""


@dataclass(frozen=True)
class IndexUpdateResult:
    added: int = 0
    updated: int = 0
    unchanged: int = 0
    deleted: int = 0


@dataclass(frozen=True)
class _VectorEntry:
    chunk: Chunk
    vector: tuple[float, ...]


def _validated_vector(vector: list[float], dimension: int) -> tuple[float, ...]:
    if len(vector) != dimension:
        raise VectorIndexError(
            f"向量维度不匹配: expected={dimension}, actual={len(vector)}"
        )
    converted = tuple(float(value) for value in vector)
    if not all(math.isfinite(value) for value in converted):
        raise VectorIndexError("向量包含非有限数值")
    if math.sqrt(sum(value * value for value in converted)) == 0:
        raise VectorIndexError("不能索引零向量")
    return converted


class InMemoryVectorIndex:
    """使用余弦相似度逐条扫描，适合测试和小型知识库。"""

    def __init__(self, space: EmbeddingSpace) -> None:
        self.space = space
        self._entries: dict[str, _VectorEntry] = {}

    def __len__(self) -> int:
        return len(self._entries)

    def chunks(self) -> list[Chunk]:
        return [entry.chunk for entry in self._entries.values()]

    def entries_for_source(self, source: str) -> list[Chunk]:
        return [
            entry.chunk
            for entry in self._entries.values()
            if entry.chunk.source == source
        ]

    def upsert(
        self,
        chunks: list[Chunk],
        vectors: list[list[float]],
    ) -> IndexUpdateResult:
        if len(chunks) != len(vectors):
            raise VectorIndexError(
                "Chunk 与 Vector 数量不匹配: "
                f"chunks={len(chunks)}, vectors={len(vectors)}"
            )

        pending: list[_VectorEntry] = []
        for chunk, vector in zip(chunks, vectors, strict=True):
            pending.append(
                _VectorEntry(
                    chunk=chunk,
                    vector=_validated_vector(vector, self.space.dimension),
                )
            )

        added = updated = unchanged = 0
        for entry in pending:
            previous = self._entries.get(entry.chunk.id)
            if previous is None:
                added += 1
            elif previous == entry:
                unchanged += 1
            else:
                updated += 1
            self._entries[entry.chunk.id] = entry

        return IndexUpdateResult(
            added=added,
            updated=updated,
            unchanged=unchanged,
        )

    def delete_chunks(self, chunk_ids: set[str]) -> int:
        deleted = 0
        for chunk_id in chunk_ids:
            if self._entries.pop(chunk_id, None) is not None:
                deleted += 1
        return deleted

    def delete_document(self, document_id: str) -> int:
        return self.delete_chunks(
            {
                chunk_id
                for chunk_id, entry in self._entries.items()
                if entry.chunk.document_id == document_id
            }
        )

    def delete_source(self, source: str) -> int:
        return self.delete_chunks(
            {
                chunk_id
                for chunk_id, entry in self._entries.items()
                if entry.chunk.source == source
            }
        )

    def clear(self) -> None:
        self._entries.clear()

    @staticmethod
    def _cosine(left: tuple[float, ...], right: tuple[float, ...]) -> float:
        dot = sum(a * b for a, b in zip(left, right, strict=True))
        left_norm = math.sqrt(sum(value * value for value in left))
        right_norm = math.sqrt(sum(value * value for value in right))
        return dot / (left_norm * right_norm)

    def search(self, query_vector: list[float], top_k: int = 5) -> list[RetrievedChunk]:
        if top_k <= 0:
            raise ValueError("top_k 必须大于 0")
        query = _validated_vector(query_vector, self.space.dimension)
        ranked = sorted(
            (
                (self._cosine(query, entry.vector), entry.chunk)
                for entry in self._entries.values()
            ),
            key=lambda item: (-item[0], item[1].id),
        )[:top_k]
        return [
            RetrievedChunk(
                chunk=chunk,
                score=score,
                retrieval_method="vector",
                rank=rank,
            )
            for rank, (score, chunk) in enumerate(ranked, start=1)
        ]

    def _payload(self) -> dict[str, Any]:
        return {
            "schema_version": INDEX_SCHEMA_VERSION,
            "embedding_space": asdict(self.space),
            "entries": [
                {
                    "chunk": entry.chunk.model_dump(mode="json"),
                    "vector": list(entry.vector),
                }
                for entry in sorted(
                    self._entries.values(), key=lambda item: item.chunk.id
                )
            ],
        }

    async def save(self, path: Path) -> None:
        payload = self._payload()

        def write_atomically() -> None:
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix(path.suffix + ".tmp")
            temporary.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            os.replace(temporary, path)

        await asyncio.to_thread(write_atomically)

    @classmethod
    async def load(
        cls,
        path: Path,
        expected_space: EmbeddingSpace | None = None,
    ) -> "InMemoryVectorIndex":
        try:
            raw = await asyncio.to_thread(path.read_text, encoding="utf-8")
            payload = json.loads(raw)
        except (OSError, json.JSONDecodeError) as exc:
            raise VectorIndexError(f"读取向量索引失败: {path}: {exc}") from exc

        if payload.get("schema_version") != INDEX_SCHEMA_VERSION:
            raise IndexMigrationRequiredError(
                "向量索引 Schema 版本不兼容: "
                f"expected={INDEX_SCHEMA_VERSION}, "
                f"actual={payload.get('schema_version')}"
            )

        try:
            space = EmbeddingSpace(**payload["embedding_space"])
        except (KeyError, TypeError, ValueError) as exc:
            raise VectorIndexError("向量索引缺少合法 Embedding Space") from exc

        if expected_space is not None and space != expected_space:
            raise IndexMigrationRequiredError(
                "Embedding 模型已变化，需要重建或迁移索引: "
                f"stored={space}, current={expected_space}"
            )

        index = cls(space)
        try:
            chunks = [Chunk.model_validate(item["chunk"]) for item in payload["entries"]]
            vectors = [item["vector"] for item in payload["entries"]]
            index.upsert(chunks, vectors)
        except (KeyError, TypeError, ValueError) as exc:
            raise VectorIndexError("向量索引 Entry 数据非法") from exc
        return index

    async def migrate_embeddings(
        self,
        provider: EmbeddingProvider,
        batch_size: int = 64,
    ) -> None:
        if batch_size <= 0:
            raise ValueError("batch_size 必须大于 0")
        chunks = self.chunks()
        vectors: list[list[float]] = []
        for start in range(0, len(chunks), batch_size):
            batch = chunks[start : start + batch_size]
            vectors.extend(
                await provider.embed_documents([chunk.text for chunk in batch])
            )

        replacement = InMemoryVectorIndex(provider.space)
        replacement.upsert(chunks, vectors)
        self.space = provider.space
        self._entries = replacement._entries
