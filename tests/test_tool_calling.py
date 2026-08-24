from app.llm import (
    parse_tool_arguments,
)
from app.tools.calculator import (
    CalculatorTool,
)

def test_calculator_tool_schema():
    schema = CalculatorTool().to_schema()
    function = schema["function"]
    assert function["name"] == "calculator"

    parameters = function["parameters"]

    assert parameters["type"] == "object"

    assert set(
        parameters["required"]
    ) == {
        "left",
        "operator",
        "right",
    }


def test_operator_schema():
    operator = (
        CalculatorTool()
        .to_schema()["function"]["parameters"]["properties"]["operator"]
    )

    assert operator["enum"] == [
        "+",
        "-",
        "*",
        "/",
    ]


def test_parse_tool_arguments():
    arguments = parse_tool_arguments(
        '{"left": 12, '
        '"operator": "*", '
        '"right": 8}'
    )

    assert arguments == {
        "left": 12,
        "operator": "*",
        "right": 8,
    }