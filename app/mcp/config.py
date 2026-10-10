from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class StdioMCPServerConfig:
    """
    一个 stdio MCP Server 的启动配置。

    这里只描述：
    Host 怎样找到并启动 Server。

    不描述 Tool。
    """

    name: str
    command: str
    args: tuple[str, ...] = ()
    env: Mapping[str, str] | None = None

    def __post_init__(
        self,
    ) -> None:

        if not self.name.strip():
            raise ValueError(
                "MCP Server name 不能为空"
            )

        if not self.command.strip():
            raise ValueError(
                "MCP Server command 不能为空"
            )