"""不依赖网络的 Agent -> RAG Tool -> Citation 端到端示例。"""

import asyncio
from pathlib import Path

from app.agent import AgentRunner
from app.providers import FakeProvider, ProviderResponse, ToolCallRequest
from app.rag.bootstrap import build_rag_runtime
from app.rag.embeddings import FakeEmbeddingProvider
from app.tools.registry import ToolRegistry


async def main() -> None:
    project_root = Path(__file__).resolve().parents[1]
    rag = await build_rag_runtime(
        workspace=project_root / "workspace",
        embedding_provider=FakeEmbeddingProvider(),
    )
    registry = ToolRegistry()
    registry.register(rag.tool)
    provider = FakeProvider(
        responses=[
            ProviderResponse(
                content="",
                tool_calls=[
                    ToolCallRequest(
                        id="demo-rag-call",
                        name="retrieve_knowledge",
                        arguments={
                            "query": "nanobot-rebuild 演示部署代号",
                            "top_k": 2,
                        },
                    )
                ],
            ),
            ProviderResponse(
                content=(
                    "演示部署代号是 Aurora-731 "
                    "[source: private_facts.md]。"
                ),
                tool_calls=[],
            ),
        ]
    )
    runner = AgentRunner(provider=provider, tool_registry=registry)
    result = await runner.run(
        [{"role": "user", "content": "项目的演示部署代号是什么？"}]
    )

    print("--- Tool Trace ---")
    print(result.tools_used[0].output)
    print("--- Final Answer ---")
    print(result.final_content)
    print("--- Index Sync ---")
    print(rag.sync_result)


if __name__ == "__main__":
    asyncio.run(main())
