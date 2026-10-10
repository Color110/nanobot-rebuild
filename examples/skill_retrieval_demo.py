import asyncio
from pathlib import Path

from app.rag.embeddings import FakeEmbeddingProvider
from app.skill_catalog import SkillCatalog
from app.skill_retriever import SkillRetriever
from app.skills import SkillLoader


async def main() -> None:
    loader = SkillLoader(
        Path("workspace")
    )

    catalog = SkillCatalog(
        loader.list_skills()
    )

    retriever = SkillRetriever(
        catalog=catalog,
        embedding_provider=FakeEmbeddingProvider(
            dimension=64
        ),
    )

    await retriever.build_index()

    results = await retriever.retrieve(
        "帮我修一下这个空指针异常",
        top_k=3,
    )

    for candidate in results:
        print(
            candidate.rank,
            candidate.skill_name,
            round(candidate.score, 4),
        )


if __name__ == "__main__":
    asyncio.run(main())