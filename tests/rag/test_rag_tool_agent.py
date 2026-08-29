from pathlib import Path

from app.agent import AgentRunner
from app.providers import FakeProvider, ProviderResponse, ToolCallRequest
from app.rag.bootstrap import build_rag_runtime
from app.rag.embeddings import FakeEmbeddingProvider
from app.tools.registry import ToolRegistry


async def test_agent_calls_rag_tool_and_receives_citable_evidence(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    knowledge = workspace / "knowledge"
    knowledge.mkdir(parents=True)
    (knowledge / "private.txt").write_text(
        "The private deployment code is Aurora-731.", encoding="utf-8"
    )
    rag = await build_rag_runtime(
        workspace=workspace,
        embedding_provider=FakeEmbeddingProvider(dimension=32),
    )
    registry = ToolRegistry()
    registry.register(rag.tool)
    provider = FakeProvider(
        responses=[
            ProviderResponse(
                content="",
                tool_calls=[
                    ToolCallRequest(
                        id="call-rag-1",
                        name="retrieve_knowledge",
                        arguments={"query": "deployment code", "top_k": 1},
                    )
                ],
            ),
            ProviderResponse(
                content="代号是 Aurora-731 [private.txt, chunk_id 已引用]。",
                tool_calls=[],
            ),
        ]
    )
    runner = AgentRunner(provider=provider, tool_registry=registry)

    result = await runner.run(
        [{"role": "user", "content": "内部部署代号是什么？"}]
    )

    assert result.tools_used[0].name == "retrieve_knowledge"
    assert "source: private.txt" in result.tools_used[0].output
    assert "chunk_id:" in result.tools_used[0].output
    assert "Aurora-731" in result.final_content
    assert provider.calls[1]["messages"][-1]["role"] == "tool"
