"""
TrustGuard search service.

Provides a pluggable search abstraction so the rest of TrustGuard does not
depend directly on a particular search provider.

The service supports:

- Multiple search adapters.
- Query variants.
- Per-query result limits.
- URL validation.
- URL normalization and deduplication.
- Search-result caching.
- Safe handling of provider failures.
- The ddgs package as the DuckDuckGo-compatible provider.

The public SearchService.multi_query_search() API uses
max_results_per_query. Callers must use that exact parameter name.
"""

from __future__ import annotations

import logging
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse


logger = logging.getLogger("trustguard.search")


# ---------------------------------------------------------------------------
# Search result model
# ---------------------------------------------------------------------------

@dataclass
class SearchResult:
    """
    Normalized search result returned by every search adapter.
    """

    title: str
    url: str
    domain: str
    snippet: str
    published_at: Optional[str]
    retrieved_at: str
    rank: int
    search_query: str
    source_type: str = "web"


# ---------------------------------------------------------------------------
# URL helpers
# ---------------------------------------------------------------------------

_TRACKING_PARAMETERS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "utm_name",
    "gclid",
    "fbclid",
    "msclkid",
    "mc_cid",
    "mc_eid",
}


def is_valid_http_url(url: str) -> bool:
    """
    Return True only for absolute HTTP/HTTPS URLs with a hostname.

    This prevents malformed search-engine URLs such as:

        https:///videos/...

    from being passed to the article extractor.
    """

    try:
        parsed = urlparse(str(url).strip())

        return (
            parsed.scheme.lower() in {"http", "https"}
            and bool(parsed.hostname)
        )

    except Exception:
        return False


def normalize_url(url: str) -> str:
    """
    Normalize a URL for deduplication.

    Tracking parameters are removed because URLs such as:

        https://example.com/article?utm_source=x
        https://example.com/article?utm_source=y

    normally refer to the same article.

    The original URL is still retained in SearchResult.url.
    """

    if not is_valid_http_url(url):
        return ""

    parsed = urlparse(url.strip())

    filtered_query = [
        (key, value)
        for key, value in parse_qsl(
            parsed.query,
            keep_blank_values=True,
        )
        if key.lower() not in _TRACKING_PARAMETERS
    ]

    normalized = parsed._replace(
        scheme=parsed.scheme.lower(),
        netloc=parsed.netloc.lower(),
        query=urlencode(filtered_query),
        fragment="",
    )

    result = urlunparse(normalized)

    if result.endswith("/") and parsed.path not in {"", "/"}:
        result = result.rstrip("/")

    return result


def get_domain(url: str) -> str:
    """Extract a normalized hostname from a valid URL."""

    if not is_valid_http_url(url):
        return ""

    try:
        return (urlparse(url).hostname or "").lower()
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Search adapter interface
# ---------------------------------------------------------------------------

class SearchAdapter(ABC):
    """
    Base interface for every search provider.

    New providers such as Bing, Google, Brave, Mojeek, etc. can implement
    this interface without changing SearchService.
    """

    name: str = "base"

    @abstractmethod
    def search(
        self,
        query: str,
        max_results: int = 10,
    ) -> list[SearchResult]:
        """
        Search one provider and return normalized results.
        """
        raise NotImplementedError


# ---------------------------------------------------------------------------
# DuckDuckGo / DDGS adapter
# ---------------------------------------------------------------------------

class DuckDuckGoSearchAdapter(SearchAdapter):
    """
    Search adapter using the modern ddgs package.

    The old duckduckgo_search package has been renamed to ddgs, so this
    implementation intentionally imports only ddgs.
    """

    name = "duckduckgo"

    def search(
        self,
        query: str,
        max_results: int = 10,
    ) -> list[SearchResult]:

        query = (query or "").strip()

        if not query:
            return []

        max_results = max(1, min(int(max_results), 50))

        try:
            from ddgs import DDGS
        except ImportError:
            logger.error(
                "[SEARCH] ddgs is not installed. "
                "Install it with: pip install -U ddgs"
            )
            return []

        results: list[SearchResult] = []

        retrieved_at = datetime.now(
            timezone.utc
        ).isoformat()

        try:
            with DDGS() as ddgs:

                items = ddgs.text(
                    query,
                    max_results=max_results,
                )

                for rank, item in enumerate(items or [], start=1):

                    if not isinstance(item, dict):
                        continue

                    raw_url = str(
                        item.get("href") or ""
                    ).strip()

                    if not is_valid_http_url(raw_url):
                        logger.debug(
                            "[SEARCH] Ignoring invalid result URL: %s",
                            raw_url,
                        )
                        continue

                    results.append(
                        SearchResult(
                            title=str(
                                item.get("title") or ""
                            ).strip(),

                            url=raw_url,

                            domain=get_domain(raw_url),

                            snippet=str(
                                item.get("body") or ""
                            ).strip(),

                            published_at=None,

                            retrieved_at=retrieved_at,

                            rank=rank,

                            search_query=query,

                            source_type="web",
                        )
                    )

        except Exception as exc:
            logger.warning(
                "[SEARCH] %s query failed (%r): %s",
                self.name,
                query,
                exc,
            )

        return results


# ---------------------------------------------------------------------------
# Search service
# ---------------------------------------------------------------------------

class SearchService:
    """
    Coordinates all registered search adapters.

    Callers should use this class rather than calling individual providers
    directly.
    """

    def __init__(
        self,
        adapters: list[SearchAdapter],
    ):
        self.adapters = list(adapters)

    def multi_query_search(
        self,
        queries: list[str],
        max_results_per_query: int = 10,
        max_results: int | None = None,
    ) -> list[SearchResult]:
   

        if max_results is not None:
            max_results_per_query = max_results

        max_results_per_query = max(
            1,
            min(int(max_results_per_query), 50),
        )

        normalized_queries = self._deduplicate_queries(queries)

        if not normalized_queries:
            return []

        seen_urls: set[str] = set()
        combined: list[SearchResult] = []

        for query in normalized_queries:
            for adapter in self.adapters:
                try:
                    adapter_results = adapter.search(
                       query,
                       max_results=max_results_per_query,
                   )
                except Exception as exc:
                    logger.warning(
                       "[SEARCH] Adapter %s failed for query %r: %s",
                        adapter.name,
                        query,
                        exc,
                    )
                   
                    continue

                for result in adapter_results:
                    if not result:
                        continue

                    normalized = normalize_url(result.url)

                    if not normalized:
                        continue

                    if normalized in seen_urls:
                        continue

                    seen_urls.add(normalized)
                    combined.append(result)

        return combined

    @staticmethod
    def _deduplicate_queries(
        queries: list[str],
    ) -> list[str]:
        """
        Normalize and deduplicate queries while preserving order.
        """

        seen: set[str] = set()
        ordered: list[str] = []

        for query in queries or []:

            value = re.sub(
                r"\s+",
                " ",
                str(query or "").strip(),
            )

            if not value:
                continue

            key = value.casefold()

            if key in seen:
                continue

            seen.add(key)
            ordered.append(value)

        return ordered


# ---------------------------------------------------------------------------
# Query generation
# ---------------------------------------------------------------------------

def build_query_variants(
    headline: str,
    entities: Optional[list[str]] = None,
) -> list[str]:
    """
    Generate conservative search variants from a headline.

    The function avoids creating unnecessary queries. This is important
    because every additional query can multiply external provider traffic.
    """

    headline = re.sub(
        r"\s+",
        " ",
        (headline or "").strip(),
    )

    if not headline:
        return []

    queries: list[str] = [
        headline,
    ]

    # Remove punctuation to catch search engines that index a normalized
    # version of the headline.
    stripped = re.sub(
        r"[^\w\s]",
        " ",
        headline,
        flags=re.UNICODE,
    )

    stripped = re.sub(
        r"\s+",
        " ",
        stripped,
    ).strip()

    if stripped and stripped.casefold() != headline.casefold():
        queries.append(stripped)

    clean_entities = []

    for entity in entities or []:

        entity = re.sub(
            r"\s+",
            " ",
            str(entity or "").strip(),
        )

        if entity:
            clean_entities.append(entity)

    if clean_entities:

        entity_query = " ".join(
            clean_entities
        )

        queries.append(entity_query)

        queries.append(
            f"{entity_query} latest"
        )

        queries.append(
            f"{entity_query} official statement"
        )

    # Final deduplication.
    seen: set[str] = set()
    ordered: list[str] = []

    for query in queries:

        query = re.sub(
            r"\s+",
            " ",
            query,
        ).strip()

        key = query.casefold()

        if not query or key in seen:
            continue

        seen.add(key)
        ordered.append(query)

    return ordered