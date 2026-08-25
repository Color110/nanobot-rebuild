from app.tools.calculator import (
    CalculatorTool,
)
from app.tools.registry import (
    ToolRegistry,
)


def create_registry() -> ToolRegistry:

    registry = ToolRegistry()

    registry.register(
        CalculatorTool()
    )

    return registry


def test_valid_tool_arguments():

    registry = create_registry()

    result = registry.execute(
        name="calculator",
        arguments={
            "left": 12,
            "operator": "*",
            "right": 8,
        },
    )

    assert result.is_error is False
    assert result.content == "96.0"


def test_wrong_argument_type():

    registry = create_registry()

    result = registry.execute(
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


def test_missing_argument():

    registry = create_registry()

    result = registry.execute(
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


def test_invalid_operator():

    registry = create_registry()

    result = registry.execute(
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


def test_extra_argument():

    registry = create_registry()

    result = registry.execute(
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


def test_execution_error():

    registry = create_registry()

    result = registry.execute(
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


def test_unknown_tool():

    registry = create_registry()

    result = registry.execute(
        name="not_exists",
        arguments={},
    )

    assert result.is_error is True

    assert (
        result.error_type
        == "UNKNOWN_TOOL"
    )