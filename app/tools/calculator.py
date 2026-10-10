from typing import Any,Literal
from app.tools.base import PydanticTool
from pydantic import BaseModel, ConfigDict, Field
class CalculatorArguments(BaseModel):
    """
    Calculator Tool 的参数模型。
    """
    model_config = ConfigDict(
        extra="forbid",
    )

    left: float = Field(
        description="左操作数",
    )
    operator: Literal["+", "-", "*", "/"] = Field(
        description="四则运算符",
    )
    right: float = Field(
        description="右操作数",
    )

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

class CalculatorTool(PydanticTool):
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
    def argument_model(self) -> type[BaseModel]:
        return CalculatorArguments
        
    async def execute(
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

