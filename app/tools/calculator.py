from typing import Any
from app.tools.base import BaseTool

def calculate(
    left: float,
    operator: str,
    right: float,
) -> float:
    """
    执行基础四则运算。

    Args:
        left: 左操作数
        operator: 运算符，支持 + - * /
        right: 右操作数

    Returns:
        计算结果

    Raises:
        ZeroDivisionError:
            除数为 0。

        ValueError:
            使用了不支持的运算符。
    """

    if operator == "+":
        return left + right

    if operator == "-":
        return left - right

    if operator == "*":
        return left * right

    if operator == "/":
        if right == 0:
            raise ZeroDivisionError(
                "除数不能为 0"
            )

        return left / right

    raise ValueError(
        f"不支持的运算符: {operator}"
    )

class CalculatorTool(BaseTool):
    @property
    def name(self) ->str:
        return "calculator"
    @property
    def description(self) -> str:
        return (
            "执行精确的基础四则运算。"
            "当用户要求进行加、减、乘、除数学计算时，"
            "应该使用此工具，而不是自行心算。"
        )
    
    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "left": {
                    "type": "number",
                    "description": "左操作数",
                },
                "operator": {
                    "type": "string",
                    "enum": ["+", "-", "*", "/"],
                    "description": "四则运算符",
                },
                "right": {
                    "type": "number",
                    "description": "右操作数",
                },
            },
            "required": [
                "left",
                "operator",
                "right",
            ],
            "additionalProperties": False,
        }
    
    def execute(
        self,
        **kwargs: Any,
    ) -> str:
        left = kwargs.get("left")
        operator = kwargs.get("operator")
        right = kwargs.get("right")

        if left is None or operator is None or right is None:
            raise ValueError(
                "缺少必要参数: left, operator, right"
            )

        result = calculate(
            left=left,
            operator=operator,
            right=right,
        )

        return str(result)
