from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SearchResult:
    title: str
    url: str
    snippet: str = ""
    source: str | None = None


@dataclass(frozen=True)
class FetchedPage:
    url: str
    final_url: str
    title: str | None
    content_type: str
    text: str
