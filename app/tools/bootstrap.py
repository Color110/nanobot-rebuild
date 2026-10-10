from pathlib import Path

from app.tools.calculator import CalculatorTool
from app.tools.current_time import CurrentTimeTool
from app.tools.fetch_web_page import FetchWebPageTool
from app.tools.registry import ToolRegistry
from app.tools.web_search import WebSearchTool
from app.tools.workspace_files import (
    ListWorkspaceFilesTool,
    WriteTextFileTool,
)
from app.tools.read_file import ReadTextFileTool

from app.web import (
    BochaSearchProvider,
    SearchProvider,
    WebPageFetcher,
)


def register_standard_tools(
    registry: ToolRegistry,
    *,
    workspace: Path,
    search_provider: SearchProvider | None = None,
) -> None:
    if search_provider is None:
        search_provider = BochaSearchProvider()

    registry.register(
        CalculatorTool()
    )

    registry.register(
        CurrentTimeTool()
    )

    registry.register(
        ReadTextFileTool(
            workspace=workspace,
        )
    )

    registry.register(
        ListWorkspaceFilesTool(
            workspace=workspace,
        )
    )

    registry.register(
        WriteTextFileTool(
            workspace=workspace,
        )
    )

    registry.register(
        WebSearchTool(
            provider=search_provider,
        )
    )

    registry.register(
        FetchWebPageTool(
            fetcher=WebPageFetcher(),
        )
    )