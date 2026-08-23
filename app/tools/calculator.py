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