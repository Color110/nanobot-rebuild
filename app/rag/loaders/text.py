"""受知识库目录约束的 UTF-8 文本文档加载器。"""

import asyncio
import hashlib
from pathlib import Path

from app.rag.document import Document


class DocumentLoadError(ValueError):
    """输入不是可摄取知识文档时抛出的稳定错误边界。"""


def _stable_document_id(source: str, text: str) -> str:
    payload = f"{source}\0{text}".encode("utf-8")
    return f"doc_{hashlib.sha256(payload).hexdigest()}"


class TextDocumentLoader:
    """异步加载知识库目录中的 UTF-8 TXT 文件。"""

    allowed_suffixes = frozenset({".txt"})
    document_format = "text"

    def __init__(
        self,
        knowledge_root: Path,
        max_file_size_bytes: int = 10 * 1024 * 1024,
    ) -> None:
        if max_file_size_bytes <= 0:
            raise ValueError("max_file_size_bytes 必须大于 0")
        self.knowledge_root = knowledge_root.resolve()
        self.max_file_size_bytes = max_file_size_bytes
        self.knowledge_root.mkdir(parents=True, exist_ok=True)

    def _resolve_target(self, path: str | Path) -> tuple[Path, str]:
        requested = Path(path)
        if requested.is_absolute():
            raise DocumentLoadError("知识文档路径必须相对于 knowledge root")

        target = (self.knowledge_root / requested).resolve()
        if not target.is_relative_to(self.knowledge_root):
            raise DocumentLoadError("禁止读取 knowledge root 之外的文件")
        if target.suffix.lower() not in self.allowed_suffixes:
            allowed = ", ".join(sorted(self.allowed_suffixes))
            raise DocumentLoadError(f"不支持的文档类型，仅允许: {allowed}")
        if not target.exists():
            raise DocumentLoadError(f"知识文档不存在: {requested}")
        if not target.is_file():
            raise DocumentLoadError(f"知识文档不是普通文件: {requested}")
        if target.stat().st_size > self.max_file_size_bytes:
            raise DocumentLoadError(
                f"知识文档超过大小限制 {self.max_file_size_bytes} bytes: "
                f"{requested}"
            )

        source = target.relative_to(self.knowledge_root).as_posix()
        return target, source

    async def load(self, path: str | Path) -> Document:
        target, source = self._resolve_target(path)
        try:
            text = await asyncio.to_thread(target.read_text, encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise DocumentLoadError(f"知识文档不是有效 UTF-8: {source}") from exc
        except OSError as exc:
            raise DocumentLoadError(f"读取知识文档失败: {source}: {exc}") from exc

        if not text.strip():
            raise DocumentLoadError(f"知识文档为空: {source}")

        stat = await asyncio.to_thread(target.stat)
        return Document(
            id=_stable_document_id(source, text),
            source=source,
            text=text,
            metadata={
                "path": source,
                "format": self.document_format,
                "size_bytes": stat.st_size,
            },
        )


class MarkdownDocumentLoader(TextDocumentLoader):
    """异步加载知识库目录中的 UTF-8 Markdown 文件。"""

    allowed_suffixes = frozenset({".md", ".markdown"})
    document_format = "markdown"
