from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from app.mcp.config import StdioMCPServerConfig
from app.mcp.manager import MCPManager
from app.mcp.sdk_client import SDKMCPClient
from app.tools.registry import ToolRegistry


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SERVER_FILE = PROJECT_ROOT / "examples" / "mcp_demo_server.py"


async def main() -> None:
    client = await SDKMCPClient.connect_stdio(
        StdioMCPServerConfig(
            name="demo",
            command=sys.executable,
            args=(str(SERVER_FILE),),
        )
    )

    registry = ToolRegistry()
    manager = MCPManager(
        registry=registry,
        clients=(client,),
    )

    try:
        await manager.start()

        print("=== Tools ===")
        for name in manager.registered_tool_names:
            print(name)

        print("\n=== Resources ===")
        for entry in manager.resource_entries:
            print(entry.server_name, entry.resource.uri, entry.resource.name)

        contents = await manager.read_resource(
            server_name="demo",
            uri="demo://guide",
        )

        print("\n=== Resource Content ===")
        for content in contents:
            print(content.text)

        print("\n=== Prompts ===")
        for entry in manager.prompt_entries:
            print(entry.local_name, entry.prompt.description)

        result = await manager.get_prompt(
            local_name="mcp__demo__prompt__explain_demo_record",
            arguments={"record_id": "A-100"},
        )

        print("\n=== Prompt Messages ===")
        for message in result.messages:
            print(f"{message.role}: {message.text}")

    finally:
        await manager.close()


if __name__ == "__main__":
    asyncio.run(main())