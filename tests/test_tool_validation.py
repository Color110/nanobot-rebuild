from app.tools.calculator import (
    CalculatorTool,
)
from app.tools.registry import (
    ToolRegistry,
)
from app.tools.read_file import (
    ReadTextFileTool,
)

def create_registry() -> ToolRegistry:

    registry = ToolRegistry()

    registry.register(
        CalculatorTool()
    )
    return registry
import pytest
@pytest.mark.asyncio
async def test_valid_tool_arguments():

    registry = create_registry()

    result = await registry.execute(
        name="calculator",
        arguments={
            "left": 12,
            "operator": "*",
            "right": 8,
        },
    )

    assert result.is_error is False
    assert result.content == "96.0"


@pytest.mark.asyncio  # 告诉 pytest 这是一个异步测试
async def test_wrong_argument_type():

    registry = create_registry()

    result = await registry.execute(
        name="calculator",
        arguments={
            "left": "12",
            "operator": "*",
            "right": 8,
        },
    )

    assert result.is_error is True

    assert (
        result.error_type
        == "VALIDATION_ERROR"
    )


@pytest.mark.asyncio  # 告诉 pytest 这是一个异步测试
async def test_missing_argument():

    registry = create_registry()

    result = await registry.execute(
        name="calculator",
        arguments={
            "left": 12,
            "right": 8,
        },
    )

    assert result.is_error is True

    assert (
        result.error_type
        == "VALIDATION_ERROR"
    )

@pytest.mark.asyncio  # 告诉 pytest 这是一个异步测试
async def test_invalid_operator():

    registry = create_registry()

    result = await registry.execute(
        name="calculator",
        arguments={
            "left": 12,
            "operator": "%",
            "right": 8,
        },
    )

    assert result.is_error is True

    assert (
        result.error_type
        == "VALIDATION_ERROR"
    )

@pytest.mark.asyncio  # 告诉 pytest 这是一个异步测试
async def test_extra_argument():

    registry = create_registry()

    result = await registry.execute(
        name="calculator",
        arguments={
            "left": 12,
            "operator": "*",
            "right": 8,
            "reason": "test",
        },
    )

    assert result.is_error is True

    assert (
        result.error_type
        == "VALIDATION_ERROR"
    )


@pytest.mark.asyncio  # 告诉 pytest 这是一个异步测试
async def test_execution_error():

    registry = create_registry()

    result = await registry.execute(
        name="calculator",
        arguments={
            "left": 10,
            "operator": "/",
            "right": 0,
        },
    )

    assert result.is_error is True

    assert (
        result.error_type
        == "EXECUTION_ERROR"
    )

    assert (
        "ZeroDivisionError"
        in result.content
    )


@pytest.mark.asyncio  # 告诉 pytest 这是一个异步测试
async def test_unknown_tool():

    registry = create_registry()

    result = await registry.execute(
        name="not_exists",
        arguments={},
    )

    assert result.is_error is True

    assert (
        result.error_type
        == "UNKNOWN_TOOL"
    )

async def test_registry_execute():
    registry = ToolRegistry()
    registry.register(CalculatorTool())

    result = await registry.execute(
        name="calculator",
        arguments={
            "left": 12,
            "operator": "*",
            "right": 8,
        },
    )

    assert result.is_error is False
    assert result.content == "96.0"

async def test_read_text_file(tmp_path):
    target = tmp_path / "hello.txt"
    target.write_text("hello agent", encoding="utf-8")

    tool = ReadTextFileTool(workspace=tmp_path)

    output = await tool.execute(path="hello.txt")

    assert output == "hello agent"