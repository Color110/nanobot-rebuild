from pathlib import Path
from typing import Any

from app.tools.base import BaseTool

class ReadTextFileTool(BaseTool):
    """
    读取 Agent workspace 中的 UTF-8 文本文件。
    """

    def __init__(
        self,
        workspace: Path,
    ) -> None:
        self.workspace = workspace.resolve()
        self.workspace.mkdir(parents=True, exist_ok=True)
    
    @property
    def name(self) -> str:
        return "read_text_file"
    
    @property
    def description(self) -> str:
        return (
            "读取 Agent workspace 中的 UTF-8 文本文件。"
            "当用户要求查看、读取或分析本地文本文件时使用。"
            "path 参数必须是相对于 workspace 的路径。"
        )
    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": (
                        "相对于 Agent workspace "
                        "的文本文件路径，"
                        "例如 notes.txt"
                    ),
                },
            },
            "required": ["path"],
            "additionalProperties": False,
        }

    def execute(self, **kwargs: Any) -> str:
        path = kwargs.get("path")

        target = (
            self.workspace / path
        ).resolve()

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

        return target.read_text(
            encoding="utf-8"
        )