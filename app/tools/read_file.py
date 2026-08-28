from pathlib import Path
from typing import Any
from abc import ABC, abstractmethod

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)

from app.tools.base import BaseTool
import asyncio

class ReadTextFileArguments(BaseModel):

    model_config = ConfigDict(
        extra="forbid"
    )

    path: str = Field(
        min_length=1,
        description=(
            "相对于 Agent workspace "
            "的 UTF-8 文本文件路径，"
            "例如 notes.txt"
        ),
    )


class ReadTextFileTool(BaseTool):

    def __init__(
        self,
        workspace: Path,
    ) -> None:

        self.workspace = workspace.resolve()

        self.workspace.mkdir(
            parents=True,
            exist_ok=True,
        )

    @property
    def name(self) -> str:
        return "read_text_file"

    @property
    def description(self) -> str:
        return (
            "读取 Agent workspace 中的 UTF-8 文本文件。"
            "当用户要求查看、读取或分析本地文本文件时使用。"
            "path 必须是相对于 workspace 的路径。"
        )

    @property
    def argument_model(
        self,
    ) -> type[BaseModel]:

        return ReadTextFileArguments

    async def execute(
        self,
        **kwargs: Any,
    ) -> str:

        path = Path(kwargs["path"])

        target = (self.workspace / path).resolve()

        if not target.is_relative_to(
            self.workspace
        ):
            raise PermissionError(
                "禁止读取 workspace 之外的文件"
            )

        if not target.exists():
            raise FileNotFoundError(
                f"文件不存在: {path}"
            )

        if not target.is_file():
            raise ValueError(
                f"目标不是文件: {path}"
            )

        return await asyncio.to_thread(
            target.read_text,
            encoding="utf-8",
        )