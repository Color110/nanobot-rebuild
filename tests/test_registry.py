import pytest

from app.tools.calculator import (
    CalculatorTool,
)
from app.tools.read_file import (
    ReadTextFileTool,
)
from app.tools.registry import (
    ToolRegistry,
)


def test_registry_register_and_get(
    tmp_path,
):

    registry = ToolRegistry()

    calculator = CalculatorTool()

    registry.register(
        calculator
    )

    assert (
        registry.get("calculator")
        is calculator
    )


def test_registry_definitions(
    tmp_path,
):

    registry = ToolRegistry()

    registry.register(
        CalculatorTool()
    )

    registry.register(
        ReadTextFileTool(
            workspace=tmp_path
        )
    )

    definitions = (
        registry.get_definitions()
    )

    names = {
        definition["function"]["name"]
        for definition in definitions
    }

    assert names == {
        "calculator",
        "read_text_file",
    }


def test_registry_execute():

    registry = ToolRegistry()

    registry.register(
        CalculatorTool()
    )

    output = registry.execute(
        name="calculator",
        arguments={
            "left": 12,
            "operator": "*",
            "right": 8,
        },
    )

    assert output == "96"


def test_duplicate_tool_name():

    registry = ToolRegistry()

    registry.register(
        CalculatorTool()
    )

    with pytest.raises(
        ValueError,
        match="Tool 已存在",
    ):
        registry.register(
            CalculatorTool()
        )


def test_unknown_tool():

    registry = ToolRegistry()

    with pytest.raises(
        KeyError,
        match="未知 Tool",
    ):
        registry.get(
            "not_exists"
        )