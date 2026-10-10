from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path

from app.tools import ToolRegistry, register_standard_tools
from app.web import FakeSearchProvider, SearchResult


async def main() -> None:
    with tempfile.TemporaryDirectory() as directory:
        workspace = Path(directory)
        registry = ToolRegistry()

        fake_search = FakeSearchProvider(
            [
                SearchResult(
                    title="Example official page",
                    url="https://example.com/official",
                    snippet="Example search snippet",
                    source="example.com",
                )
            ]
        )

        register_standard_tools(
            registry,
            workspace=workspace,
            search_provider=fake_search,
        )

        expected = {
            "calculator",
            "read_text_file",
            "list_workspace_files",
            "write_text_file",
            "current_time",
            "web_search",
            "fetch_web_page",
        }
        assert expected.issubset(set(registry.names()))

        search = await registry.execute(
            "web_search",
            {"query": "demo", "max_results": 3},
        )
        assert not search.is_error
        search_payload = json.loads(search.content)
        assert search_payload["trust"] == "untrusted_external_content"
        assert search_payload["results"][0]["url"] == "https://example.com/official"

        write = await registry.execute(
            "write_text_file",
            {
                "path": "reports/demo.txt",
                "content": "M7 tool smoke",
                "overwrite": False,
            },
        )
        assert not write.is_error, write.to_llm_content()

        read = await registry.execute(
            "read_text_file",
            {"path": "reports/demo.txt"},
        )
        assert not read.is_error
        assert read.content == "M7 tool smoke"

        listing = await registry.execute(
            "list_workspace_files",
            {
                "path": ".",
                "recursive": True,
                "max_entries": 20,
            },
        )
        assert not listing.is_error
        listing_payload = json.loads(listing.content)
        assert any(
            item["path"] == "reports/demo.txt"
            for item in listing_payload["entries"]
        )

        current_time = await registry.execute(
            "current_time",
            {"timezone": "UTC"},
        )
        assert not current_time.is_error
        assert json.loads(current_time.content)["timezone"] == "UTC"

        private_fetch = await registry.execute(
            "fetch_web_page",
            {"url": "http://127.0.0.1:8000/private"},
        )
        assert private_fetch.is_error
        assert private_fetch.error_type == "WEB_FETCH_ERROR"

        traversal = await registry.execute(
            "write_text_file",
            {
                "path": "../escape.txt",
                "content": "blocked",
                "overwrite": False,
            },
        )
        assert traversal.is_error
        assert traversal.error_type == "WORKSPACE_PATH_DENIED"

        print("Registered tools:", sorted(registry.names()))
        print("Web search fake provider: PASS")
        print("Workspace read/write/list: PASS")
        print("Current time: PASS")
        print("Private-network fetch block: PASS")
        print("Workspace traversal block: PASS")
        print("TOOLS CAPABILITY SMOKE PASSED")


if __name__ == "__main__":
    asyncio.run(main())
