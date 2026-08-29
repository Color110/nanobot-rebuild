"""J1 首个检查点：加载并切分一个本地知识文档。"""

import asyncio
from pathlib import Path

from app.rag.chunker import TokenChunker
from app.rag.loaders import MarkdownDocumentLoader


async def main() -> None:
    project_root = Path(__file__).resolve().parents[1]
    knowledge_root = project_root / "workspace" / "knowledge"
    document = await MarkdownDocumentLoader(knowledge_root).load(
        "private_facts.md"
    )
    chunks = TokenChunker(
        chunk_size_tokens=24,
        overlap_tokens=4,
    ).chunk(document)

    print(f"document_id={document.id}")
    print(f"source={document.source}")
    print(f"chunks={len(chunks)}")
    for chunk in chunks:
        print(
            f"- {chunk.id[:20]}... "
            f"tokens=[{chunk.start_token}, {chunk.end_token}) "
            f"text={chunk.text!r}"
        )


if __name__ == "__main__":
    asyncio.run(main())
