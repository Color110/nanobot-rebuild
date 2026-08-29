"""使用环境变量执行一次真实 Embedding API 冒烟实验。"""

import asyncio

from app.rag.embeddings import OpenAICompatibleEmbeddingProvider


async def main() -> None:
    provider = OpenAICompatibleEmbeddingProvider.from_env()
    try:
        vector = await provider.embed_query("nanobot-rebuild real provider check")
        print(f"space={provider.space}")
        print(f"vector_dimension={len(vector)}")
        print(f"trace={provider.trace_collector.summary()}")
    finally:
        await provider.close()


if __name__ == "__main__":
    asyncio.run(main())
