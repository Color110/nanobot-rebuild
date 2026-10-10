from __future__ import annotations

import asyncio

from app.tools import ToolRegistry, register_standard_tools


async def main() -> None:
    registry = ToolRegistry()
    register_standard_tools(
        registry,
        workspace=__import__("pathlib").Path("workspace"),
    )

    search = await registry.execute(
        "web_search",
        {
            "query": "OpenAI official site",
            "max_results": 3,
        },
    )
    print("=== web_search ===")
    print(search.to_llm_content())

    if search.is_error:
        return

    import json

    results = json.loads(search.content).get("results", [])
    if not results:
        print("No results returned; search HTML surface may have changed.")
        return

    page = await registry.execute(
        "fetch_web_page",
        {"url": results[0]["url"]},
    )
    print("\n=== fetch_web_page ===")
    print(page.to_llm_content()[:4000])


if __name__ == "__main__":
    asyncio.run(main())
