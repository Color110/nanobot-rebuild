import pytest

from app.commands import (
    parse_calculator_command,
)


def test_parse_calculator_command():
    left, operator, right = (
        parse_calculator_command(
            "/calc 12 * 8"
        )
    )

    assert left == 12
    assert operator == "*"
    assert right == 8


def test_invalid_calculator_command():
    with pytest.raises(ValueError):
        parse_calculator_command(
            "/calc hello * 8"
        )