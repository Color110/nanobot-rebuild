from __future__ import annotations

import asyncio
import json
import sys

from pathlib import Path
from typing import Any


SERVER_FILE = (
    Path(__file__)
    .with_name(
        "stdio_server.py"
    )
)


class JsonRpcError(
    RuntimeError
):

    def __init__(
        self,
        *,
        code: int,
        message: str,
    ) -> None:

        super().__init__(
            f"{code}: {message}"
        )

        self.code = code
        self.message = message


class StdioLearningClient:

    def __init__(self) -> None:

        self._process: (
            asyncio.subprocess.Process
            | None
        ) = None

        self._next_id = 1

    async def start(
        self,
    ) -> None:

        self._process = (
            await asyncio.create_subprocess_exec(
                sys.executable,
                str(SERVER_FILE),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        )

    def _require_process(
        self,
    ) -> asyncio.subprocess.Process:

        if self._process is None:
            raise RuntimeError(
                "server process "
                "has not been started"
            )

        return self._process

    async def _write_message(
        self,
        message: dict[str, Any],
    ) -> None:

        process = (
            self._require_process()
        )

        if process.stdin is None:
            raise RuntimeError(
                "server stdin unavailable"
            )

        payload = (
            json.dumps(
                message,
                ensure_ascii=False,
                separators=(",", ":"),
            )
            + "\n"
        ).encode(
            "utf-8"
        )

        process.stdin.write(
            payload
        )

        await process.stdin.drain()

    async def request(
        self,
        *,
        method: str,
        params: (
            dict[str, Any]
            | None
        ) = None,
    ) -> Any:

        process = (
            self._require_process()
        )

        if process.stdout is None:
            raise RuntimeError(
                "server stdout unavailable"
            )

        request_id = self._next_id
        self._next_id += 1

        await self._write_message(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": method,
                "params": (
                    params or {}
                ),
            }
        )

        raw = await (
            process.stdout.readline()
        )

        if not raw:

            raise RuntimeError(
                "server closed stdout"
            )

        try:
            response = json.loads(
                raw.decode("utf-8")
            )

        except json.JSONDecodeError as exc:

            raise RuntimeError(
                "invalid JSON-RPC "
                "response from server"
            ) from exc

        if (
            response.get("id")
            != request_id
        ):

            raise RuntimeError(
                "response id mismatch"
            )

        if "error" in response:

            error = response[
                "error"
            ]

            raise JsonRpcError(
                code=error.get(
                    "code",
                    -1,
                ),
                message=error.get(
                    "message",
                    "unknown error",
                ),
            )

        return response.get(
            "result"
        )

    async def notify(
        self,
        *,
        method: str,
        params: (
            dict[str, Any]
            | None
        ) = None,
    ) -> None:

        await self._write_message(
            {
                "jsonrpc": "2.0",
                "method": method,
                "params": (
                    params or {}
                ),
            }
        )

    async def initialize(
        self,
    ) -> None:

        result = await self.request(
            method="initialize",
            params={
                "protocolVersion": (
                    "learning-1"
                ),
                "capabilities": {},
                "clientInfo": {
                    "name": (
                        "learning-client"
                    ),
                    "version": "0.1",
                },
            },
        )

        if (
            result["protocolVersion"]
            != "learning-1"
        ):

            raise RuntimeError(
                "protocol version mismatch"
            )

        await self.notify(
            method=(
                "notifications/"
                "initialized"
            )
        )

    async def list_tools(
        self,
    ) -> tuple[
        dict[str, Any],
        ...
    ]:

        result = await self.request(
            method="tools/list"
        )

        return tuple(
            result["tools"]
        )

    async def call_tool(
        self,
        *,
        name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:

        result = await self.request(
            method="tools/call",
            params={
                "name": name,
                "arguments": arguments,
            },
        )

        return result

    async def close(
        self,
    ) -> None:

        process = self._process

        if process is None:
            return

        if process.stdin is not None:
            process.stdin.close()

        try:

            await asyncio.wait_for(
                process.wait(),
                timeout=1.0,
            )

        except TimeoutError:

            process.kill()

            await process.wait()

        self._process = None


async def main() -> None:

    client = StdioLearningClient()

    await client.start()

    try:

        print(
            "[1] server process started"
        )

        await client.initialize()

        print(
            "[2] MCP initialized"
        )

        tools = (
            await client.list_tools()
        )

        print(
            "[3] tools:"
        )

        for tool in tools:

            print(
                "   ",
                tool["name"],
                "-",
                tool["description"],
            )

        result = (
            await client.call_tool(
                name="multiply",
                arguments={
                    "a": 6,
                    "b": 7,
                },
            )
        )

        print(
            "[4] result:",
            result["content"][0][
                "text"
            ],
        )

    finally:

        await client.close()


if __name__ == "__main__":

    asyncio.run(
        main()
    )