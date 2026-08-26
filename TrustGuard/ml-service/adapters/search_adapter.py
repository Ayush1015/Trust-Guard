"""
Phase II-B: pluggable search abstraction. DuckDuckGo is the first
concrete adapter because it needs no API key to get you unblocked;
Google/Bing can be added later as siblings without touching callers.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse

logger = logging.getLogger("trustguard.search")


@dataclass
class SearchResult:
    title: str
    url: str
    domain: str
    snippet: str
    published_at: Optional[str]
    retrieved_at: str
    rank: int
    search_query: str
    source_type: str = "web"


class SearchAdapter(ABC):

    name: str = "base"

    @abstractmethod
    def search(self, query: str, max_results: int = 8) -> list[SearchResult]:
        ...


class DuckDuckGoSearchAdapter(SearchAdapter):
    name = "duckduckgo"

    def search(self, query: str, max_results: int = 8) -> list[SearchResult]:
        try:
            from duckduckgo_search import DDGS
        except ImportError:
            logger.warning(
                "[SEARCH] duckduckgo_search not installed. "
                "Run: pip install duckduckgo-search"
            )
            return []

        results: list[SearchResult] = []
        retrieved_at = datetime.now(timezone.utc).isoformat()

        try:
            with DDGS() as ddgs:
                for rank, item in enumerate(ddgs.text(query, max_results=max_results)):
                    url = item.get("href", "")
                    if not url:
                        continue
                    results.append(SearchResult(
                        title=item.get("title", ""),
                        url=url,

                        domain=(urlparse(url).hostname or "").lower(),
                        snippet=item.get("body", ""),
                        published_at=None,  # DDG text search has no reliable date
                        retrieved_at=retrieved_at,
                        rank=rank,
                        search_query=query,
                    ))
        except Exception as exc:
            logger.warning("[SEARCH] DuckDuckGo query failed (%r): %s", query, exc)

        return results


class SearchService:
    """Fans a set of generated queries out across every registered
    adapter, deduplicating by URL. This is what §4/§10 call for —
    the caller never talks to DuckDuckGo/Google/Bing directly."""

    def __init__(self, adapters: list[SearchAdapter]):
        self.adapters = adapters

    def multi_query_search(self, queries: list[str], max_results_per_query: int = 6) -> list[SearchResult]:
        seen_urls: set[str] = set()
        combined: list[SearchResult] = []

        for query in queries:
            for adapter in self.adapters:
                for result in adapter.search(query, max_results=max_results_per_query):
                    if result.url in seen_urls:
                        continue
                    seen_urls.add(result.url)
                    combined.append(result)


        return combined


def build_query_variants(headline: str, entities: Optional[list[str]] = None) -> list[str]:
    """§4's query-generation strategy, generalized (no hard-coded topics)."""
    headline = (headline or "").strip()
    if not headline:
        return []

    entity_str = " ".join(entities or [])
    queries = [headline]

    stripped = "".join(c for c in headline if c.isalnum() or c.isspace()).strip()
    if stripped and stripped != headline:
        queries.append(stripped)

    if entity_str:
        queries.append(entity_str)
        queries.append(f"{entity_str} latest")
        queries.append(f"{entity_str} official statement")

    # De-dup while preserving order
    seen = set()
    ordered = []
    for q in queries:
        if q and q not in seen:
            seen.add(q)
            ordered.append(q)
    return ordered