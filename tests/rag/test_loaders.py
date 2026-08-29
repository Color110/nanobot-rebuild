from pathlib import Path

import pytest

from app.rag.loaders import (
    DocumentLoadError,
    MarkdownDocumentLoader,
    TextDocumentLoader,
)


async def test_text_loader_returns_stable_document_with_relative_source(
    tmp_path: Path,
) -> None:
    knowledge = tmp_path / "knowledge"
    target = knowledge / "team" / "facts.txt"
    target.parent.mkdir(parents=True)
    target.write_text("项目暗号是 Aurora-731。", encoding="utf-8")
    loader = TextDocumentLoader(knowledge)

    first = await loader.load("team/facts.txt")
    second = await loader.load(Path("team/facts.txt"))

    assert first == second
    assert first.id.startswith("doc_")
    assert first.source == "team/facts.txt"
    assert first.metadata == {
        "path": "team/facts.txt",
        "format": "text",
        "size_bytes": target.stat().st_size,
    }


async def test_markdown_loader_accepts_markdown_and_marks_format(
    tmp_path: Path,
) -> None:
    knowledge = tmp_path / "knowledge"
    knowledge.mkdir()
    (knowledge / "guide.md").write_text("# 指南\n\n仅供内部使用。", encoding="utf-8")

    document = await MarkdownDocumentLoader(knowledge).load("guide.md")

    assert document.source == "guide.md"
    assert document.metadata["format"] == "markdown"


@pytest.mark.parametrize("path", ["../secret.txt", "nested/../../secret.txt"])
async def test_loader_blocks_directory_traversal(tmp_path: Path, path: str) -> None:
    knowledge = tmp_path / "knowledge"
    knowledge.mkdir()

    with pytest.raises(DocumentLoadError, match="之外"):
        await TextDocumentLoader(knowledge).load(path)


async def test_loader_rejects_absolute_path(tmp_path: Path) -> None:
    knowledge = tmp_path / "knowledge"
    knowledge.mkdir()
    target = knowledge / "facts.txt"
    target.write_text("fact", encoding="utf-8")

    with pytest.raises(DocumentLoadError, match="相对于"):
        await TextDocumentLoader(knowledge).load(target)


async def test_loader_rejects_empty_and_invalid_utf8_files(tmp_path: Path) -> None:
    knowledge = tmp_path / "knowledge"
    knowledge.mkdir()
    (knowledge / "empty.txt").write_text("  \n", encoding="utf-8")
    (knowledge / "invalid.txt").write_bytes(b"\xff\xfe")
    loader = TextDocumentLoader(knowledge)

    with pytest.raises(DocumentLoadError, match="为空"):
        await loader.load("empty.txt")
    with pytest.raises(DocumentLoadError, match="UTF-8"):
        await loader.load("invalid.txt")


async def test_loader_rejects_wrong_extension(tmp_path: Path) -> None:
    knowledge = tmp_path / "knowledge"
    knowledge.mkdir()
    (knowledge / "data.json").write_text("{}", encoding="utf-8")

    with pytest.raises(DocumentLoadError, match="不支持"):
        await TextDocumentLoader(knowledge).load("data.json")
