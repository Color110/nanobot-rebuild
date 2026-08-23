import pytest

from app.tools.calculator import calculate


def test_add():
    result = calculate(
        10,
        "+",
        5,
    )

    assert result == 15


def test_subtract():
    result = calculate(
        10,
        "-",
        5,
    )

    assert result == 5


def test_multiply():
    result = calculate(
        12,
        "*",
        8,
    )

    assert result == 96


def test_divide():
    result = calculate(
        10,
        "/",
        2,
    )

    assert result == 5


def test_divide_by_zero():
    with pytest.raises(
        ZeroDivisionError
    ):
        calculate(
            10,
            "/",
            0,
        )


def test_invalid_operator():
    with pytest.raises(
        ValueError
    ):
        calculate(
            10,
            "%",
            3,
        )