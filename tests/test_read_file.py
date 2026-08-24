import pytest

from app.tools.read_file import (
    ReadTextFileTool,
)


def test_read_text_file(
    tmp_path,
):

    target = (
        tmp_path / "hello.txt"
    )

    target.write_text(
        "hello agent",
        encoding="utf-8",
    )

    tool = ReadTextFileTool(
        workspace=tmp_path
    )

    output = tool.execute(
        path="hello.txt"
    )

    assert output == "hello agent"


def test_missing_file(
    tmp_path,
):

    tool = ReadTextFileTool(
        workspace=tmp_path
    )

    with pytest.raises(
        FileNotFoundError
    ):
        tool.execute(
            path="missing.txt"
        )


def test_cannot_escape_workspace(
    tmp_path,
):

    workspace = (
        tmp_path / "workspace"
    )

    workspace.mkdir()

    outside = (
        tmp_path / "secret.txt"
    )

    outside.write_text(
        "secret",
        encoding="utf-8",
    )

    tool = ReadTextFileTool(
        workspace=workspace
    )

    with pytest.raises(
        PermissionError
    ):
        tool.execute(
            path="../secret.txt"
        )