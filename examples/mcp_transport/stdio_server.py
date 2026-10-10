from __future__ import annotations

import json
import sys
from typing import Any


PROTOCOL_VERSION = "learning-1"

initialized = False
ready = False


TOOLS = [
    {
        "name": "multiply",
        "description": "计算两个整数的乘积",
        "inputSchema": {
            "type": "object",
            "properties": {
                "a": {
                    "type": "integer",
                },
                "b": {
                    "type": "integer",
                },
            },
            "required": [
                "a",
                "b",
            ],
        },
    }
]


def write_message(
    message: dict[str, Any],
) -> None:

    text = json.dumps(
        message,
        ensure_ascii=False,
        separators=(",", ":"),
    )

    sys.stdout.write(
        text + "\n"
    )

    sys.stdout.flush()


def write_error(
    request_id: Any,
    *,
    code: int,
    message: str,
) -> None:

    write_message(
        {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {
                "code": code,
                "message": message,
            },
        }
    )


def handle_request(
    message: dict[str, Any],
) -> None:

    global initialized
    global ready

    method = message.get(
        "method"
    )

    request_id = message.get(
        "id"
    )

    params = message.get(
        "params"
    ) or {}

    # --------------------------------------------
    # initialize request
    # --------------------------------------------

    if method == "initialize":

        client_version = params.get(
            "protocolVersion"
        )

        if (
            client_version
            != PROTOCOL_VERSION
        ):
            write_error(
                request_id,
                code=-32602,
                message=(
                    "protocol version mismatch"
                ),
            )
            return

        initialized = True

        write_message(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "protocolVersion": (
                        PROTOCOL_VERSION
                    ),
                    "capabilities": {
                        "tools": {},
                    },
                    "serverInfo": {
                        "name": (
                            "learning-stdio-server"
                        ),
                        "version": "0.1",
                    },
                },
            }
        )

        return

    # --------------------------------------------
    # initialized notification
    # --------------------------------------------

    if (
        method
        == "notifications/initialized"
    ):

        if initialized:
            ready = True

        # Notification 不返回 Response
        return

    # --------------------------------------------
    # normal requests require READY
    # --------------------------------------------

    if not ready:

        write_error(
            request_id,
            code=-32000,
            message="server is not ready",
        )

        return

    # --------------------------------------------
    # tools/list
    # --------------------------------------------

    if method == "tools/list":

        write_message(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "tools": TOOLS,
                },
            }
        )

        return

    # --------------------------------------------
    # tools/call
    # --------------------------------------------

    if method == "tools/call":

        name = params.get(
            "name"
        )

        arguments = params.get(
            "arguments"
        ) or {}

        if name != "multiply":

            write_error(
                request_id,
                code=-32602,
                message=(
                    f"unknown tool: {name}"
                ),
            )

            return

        a = arguments.get("a")
        b = arguments.get("b")

        if (
            not isinstance(a, int)
            or not isinstance(b, int)
        ):

            write_message(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "content": [
                            {
                                "type": "text",
                                "text": (
                                    "a and b "
                                    "must be integers"
                                ),
                            }
                        ],
                        "isError": True,
                    },
                }
            )

            return

        result = a * b

        write_message(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": str(result),
                        }
                    ],
                    "isError": False,
                },
            }
        )

        return

    write_error(
        request_id,
        code=-32601,
        message=(
            f"unknown method: {method}"
        ),
    )


def main() -> None:

    # 日志必须走 stderr
    print(
        "[server] started",
        file=sys.stderr,
        flush=True,
    )

    for line in sys.stdin:

        line = line.strip()

        if not line:
            continue

        try:
            message = json.loads(
                line
            )

        except json.JSONDecodeError:

            write_error(
                None,
                code=-32700,
                message="parse error",
            )

            continue

        if (
            message.get("jsonrpc")
            != "2.0"
        ):

            write_error(
                message.get("id"),
                code=-32600,
                message="invalid request",
            )

            continue

        handle_request(
            message
        )


if __name__ == "__main__":
    main()