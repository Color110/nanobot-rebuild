def parse_calculator_command(
    command: str,
    ) -> tuple[float,str,float]:
    """
    将：

        /calc 12 * 8

    解析成：

        (12.0, "*", 8.0)
    """
    parts = command.split()
    if len(parts) != 4:
        raise ValueError(
            "计算器命令格式错误，"
            "正确格式：/calc 数字 运算符 数字"
        )
    if parts[0] != "/calc":
        raise ValueError(
            "不是计算器命令"
        )
    operator = parts[2]
    try:
        left = float(parts[1])
        right = float(parts[3])
    except ValueError as exc:
        raise ValueError(
            "计算器命令中的数字格式错误"
        ) from exc
    return left, operator, right