"""基于 Token 窗口的确定性文档切分。"""

import hashlib

import tiktoken

from app.rag.document import Chunk, Document


class TokenChunker:
    """按模型 Token 切分文档，并在相邻 Chunk 间保留重叠。"""

    def __init__(
        self,
        chunk_size_tokens: int = 400,
        overlap_tokens: int = 60,
        encoding_name: str = "o200k_base",
    ) -> None:
        if chunk_size_tokens <= 0:
            raise ValueError("chunk_size_tokens 必须大于 0")
        if overlap_tokens < 0:
            raise ValueError("overlap_tokens 不能小于 0")
        if overlap_tokens >= chunk_size_tokens:
            raise ValueError("overlap_tokens 必须小于 chunk_size_tokens")

        self.chunk_size_tokens = chunk_size_tokens
        self.overlap_tokens = overlap_tokens
        self.encoding_name = encoding_name
        self._encoding = tiktoken.get_encoding(encoding_name)

    @staticmethod
    def _chunk_id(
        document_id: str,
        index: int,
        start_token: int,
        end_token: int,
        text: str,
    ) -> str:
        payload = (
            f"{document_id}\0{index}\0{start_token}\0{end_token}\0{text}"
        ).encode("utf-8")
        return f"chunk_{hashlib.sha256(payload).hexdigest()}"

    def chunk(self, document: Document) -> list[Chunk]:
        tokens = self._encoding.encode(document.text)
        if not tokens:
            return []

        chunks: list[Chunk] = []
        step = self.chunk_size_tokens - self.overlap_tokens

        for index, start_token in enumerate(range(0, len(tokens), step)):
            end_token = min(start_token + self.chunk_size_tokens, len(tokens))
            chunk_tokens = tokens[start_token:end_token]
            text = self._encoding.decode(chunk_tokens)

            chunks.append(
                Chunk(
                    id=self._chunk_id(
                        document.id,
                        index,
                        start_token,
                        end_token,
                        text,
                    ),
                    document_id=document.id,
                    source=document.source,
                    text=text,
                    index=index,
                    token_count=len(chunk_tokens),
                    start_token=start_token,
                    end_token=end_token,
                    metadata=dict(document.metadata),
                )
            )

            if end_token == len(tokens):
                break

        return chunks
