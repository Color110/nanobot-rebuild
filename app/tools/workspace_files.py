from __future__ import annotations

import asyncio
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.tools.base import PydanticTool, ToolExecutionError


def _resolve_inside_workspace(
    workspace: Path,
    relative_path: str,
) -> Path:
    path = Path(relative_path)
    if path.is_absolute():
        raise ToolExecutionError(
            "path 必须是 workspace 内的相对路径",
            error_type="WORKSPACE_PATH_DENIED",
        )

    target = (workspace / path).resolve()
    if not target.is_relative_to(workspace):
        raise ToolExecutionError(
            "禁止访问 workspace 之外的路径",
            error_type="WORKSPACE_PATH_DENIED",
        )
    return target


class ListWorkspaceFilesArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str = Field(
        default=".",
        max_length=512,
        description="相对于 workspace 的目录路径，默认当前 workspace。",
    )
    recursive: bool = Field(
        default=False,
        description="是否递归列出子目录。",
    )
    max_entries: int = Field(
        default=100,
        ge=1,
        le=500,
        description="最多返回的文件/目录条目数量。",
    )


class ListWorkspaceFilesTool(PydanticTool):
    def __init__(self, workspace: Path) -> None:
        self._workspace = workspace.resolve()
        self._workspace.mkdir(parents=True, exist_ok=True)

    @property
    def name(self) -> str:
        return "list_workspace_files"

    @property
    def description(self) -> str:
        return (
            "列出 Agent workspace 内的文件和目录。"
            "适合在调用 read_text_file 前发现可用文件名；"
            "不会访问 workspace 之外的路径。"
        )

    @property
    def argument_model(self) -> type[BaseModel]:
        return ListWorkspaceFilesArguments

    async def execute(self, **kwargs: Any) -> str:
        target = _resolve_inside_workspace(
            self._workspace,
            kwargs["path"],
        )
        if not target.exists():
            raise ToolExecutionError(
                f"目录不存在: {kwargs['path']}",
                error_type="WORKSPACE_NOT_FOUND",
            )
        if not target.is_dir():
            raise ToolExecutionError(
                f"目标不是目录: {kwargs['path']}",
                error_type="WORKSPACE_NOT_DIRECTORY",
            )

        entries = await asyncio.to_thread(
            self._list_entries,
            target,
            kwargs["recursive"],
            kwargs["max_entries"],
        )
        return json.dumps(
            {
                "path": kwargs["path"],
                "recursive": kwargs["recursive"],
                "entries": entries,
            },
            ensure_ascii=False,
        )

    def _list_entries(
        self,
        target: Path,
        recursive: bool,
        max_entries: int,
    ) -> list[dict[str, Any]]:
        iterator = target.rglob("*") if recursive else target.iterdir()
        output: list[dict[str, Any]] = []

        for item in sorted(iterator, key=lambda path: str(path).lower()):
            try:
                resolved = item.resolve()
                if not resolved.is_relative_to(self._workspace):
                    continue
                stat = item.stat()
            except (OSError, RuntimeError):
                continue

            output.append(
                {
                    "path": item.relative_to(self._workspace).as_posix(),
                    "type": "directory" if item.is_dir() else "file",
                    "size_bytes": stat.st_size if item.is_file() else None,
                }
            )
            if len(output) >= max_entries:
                break

        return output


class WriteTextFileArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str = Field(
        min_length=1,
        max_length=512,
        description="相对于 workspace 的目标文本文件路径。",
    )
    content: str = Field(
        max_length=200_000,
        description="需要写入的 UTF-8 文本内容。",
    )
    overwrite: bool = Field(
        default=False,
        description="目标已存在时是否允许覆盖。默认 false。",
    )


class WriteTextFileTool(PydanticTool):
    def __init__(self, workspace: Path) -> None:
        self._workspace = workspace.resolve()
        self._workspace.mkdir(parents=True, exist_ok=True)

    @property
    def name(self) -> str:
        return "write_text_file"

    @property
    def description(self) -> str:
        return (
            "把 UTF-8 文本写入 Agent workspace。这个工具会产生文件副作用；"
            "默认不覆盖已有文件，只有 overwrite=true 时才允许覆盖。"
        )

    @property
    def argument_model(self) -> type[BaseModel]:
        return WriteTextFileArguments

    async def execute(self, **kwargs: Any) -> str:
        target = _resolve_inside_workspace(
            self._workspace,
            kwargs["path"],
        )

        if target.exists() and not target.is_file():
            raise ToolExecutionError(
                f"目标不是普通文件: {kwargs['path']}",
                error_type="WORKSPACE_NOT_FILE",
            )

        try:
            if kwargs["overwrite"]:
                await asyncio.to_thread(
                    self._atomic_replace,
                    target,
                    kwargs["content"],
                )
            else:
                await asyncio.to_thread(
                    self._exclusive_write,
                    target,
                    kwargs["content"],
                )
        except FileExistsError as exc:
            raise ToolExecutionError(
                f"文件已存在，overwrite=false: {kwargs['path']}",
                error_type="WORKSPACE_FILE_EXISTS",
            ) from exc

        return json.dumps(
            {
                "path": target.relative_to(self._workspace).as_posix(),
                "bytes_written": len(kwargs["content"].encode("utf-8")),
                "overwritten": bool(kwargs["overwrite"]),
            },
            ensure_ascii=False,
        )

    @staticmethod
    def _exclusive_write(target: Path, content: str) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        file_descriptor = os.open(
            target,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
        )
        try:
            with os.fdopen(file_descriptor, "w", encoding="utf-8") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
        except Exception:
            target.unlink(missing_ok=True)
            raise

    @staticmethod
    def _atomic_replace(target: Path, content: str) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        file_descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{target.name}.",
            suffix=".tmp",
            dir=str(target.parent),
        )
        temporary_path = Path(temporary_name)
        try:
            with os.fdopen(file_descriptor, "w", encoding="utf-8") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_path, target)
        except Exception:
            try:
                temporary_path.unlink(missing_ok=True)
            finally:
                raise
