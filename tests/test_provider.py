import pytest

from app.providers import FakeProvider, ProviderResponse


async def test_fake_provider_returns_responses_in_order():
    provider = FakeProvider(
        responses=[
            ProviderResponse(
                content="first",
                tool_calls=[],
            ),
            ProviderResponse(
                content="second",
                tool_calls=[],
            ),
        ]
    )

    first = await provider.complete(messages=[])
    second = await provider.complete(messages=[])

    assert first.content == "first"
    assert second.content == "second"

@pytest.mark.asyncio  # 告诉 pytest 这是一个异步测试
async def test_fake_provider_fails_when_responses_exhausted():
    provider = FakeProvider(responses=[])

    with pytest.raises(
        RuntimeError,
        match="没有剩余",
    ):
        await provider.complete(messages=[])

import pytest

from app.providers import ProviderError
from app.providers.openai_compatible import parse_tool_arguments


def test_parse_tool_arguments():
    arguments = parse_tool_arguments(
        '{"left": 12, "operator": "*", "right": 8}'
    )

    assert arguments == {
        "left": 12,
        "operator": "*",
        "right": 8,
    }


def test_tool_arguments_must_be_object():
    with pytest.raises(
        ProviderError,
        match="JSON object",
    ):
        parse_tool_arguments("[1, 2, 3]")


def test_invalid_tool_arguments_json():
    with pytest.raises(
        ProviderError,
        match="非法",
    ):
        parse_tool_arguments("{broken-json")

from app.providers import OpenAICompatibleProvider


def test_provider_from_env_requires_api_key(monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.setenv("LLM_MODEL", "test-model")

    with pytest.raises(
        RuntimeError,
        match="LLM_API_KEY",
    ):
        OpenAICompatibleProvider.from_env()


def test_provider_from_env_requires_model(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.delenv("LLM_MODEL", raising=False)

    with pytest.raises(
        RuntimeError,
        match="LLM_MODEL",
    ):
        OpenAICompatibleProvider.from_env()