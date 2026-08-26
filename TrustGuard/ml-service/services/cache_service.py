"""
TrustGuard cache service.

Provides small, thread-safe, in-memory TTL caches for:
- Gemini news-verification results
- Search results
- Extracted article content

The cache is intentionally in-memory so it requires no Redis or other
external infrastructure. It resets when the process restarts.

TTL values are deliberately different for each cache:

- Gemini verification: short TTL because verification depends on current
  web information.
- Search results: short TTL because search rankings/results can change.
- Article content: longer TTL because published article text is generally
  stable.

The public interface is intentionally small so this implementation can be
replaced by Redis later without changing callers.
"""

from __future__ import annotations

import hashlib
import re
import threading
import time
from dataclasses import dataclass
from typing import Any, Optional


# ---------------------------------------------------------------------------
# Default cache configuration
# ---------------------------------------------------------------------------

GEMINI_CACHE_TTL_SECONDS = 300       # 5 minutes
SEARCH_CACHE_TTL_SECONDS = 900       # 15 minutes
ARTICLE_CACHE_TTL_SECONDS = 21600    # 6 hours

GEMINI_CACHE_MAX_ENTRIES = 500
SEARCH_CACHE_MAX_ENTRIES = 300
ARTICLE_CACHE_MAX_ENTRIES = 1000


# ---------------------------------------------------------------------------
# Cache entry
# ---------------------------------------------------------------------------

@dataclass
class _Entry:
    value: Any
    expires_at: float


# ---------------------------------------------------------------------------
# Generic in-memory TTL cache
# ---------------------------------------------------------------------------

class TTLCache:
    """
    Thread-safe in-memory cache with expiration.

    time.monotonic() is used for expiration instead of wall-clock time so
    system clock changes cannot unexpectedly extend or shorten cache entries.
    """

    def __init__(
        self,
        default_ttl: int,
        max_entries: int = 500,
    ):
        self._store: dict[str, _Entry] = {}
        self._lock = threading.Lock()
        self._default_ttl = max(0, int(default_ttl))
        self._max_entries = max(1, int(max_entries))

        self.hits = 0
        self.misses = 0

    def get(self, key: str) -> Optional[Any]:
        """
        Return a cached value when it exists and has not expired.

        Expired entries are removed immediately when accessed.
        """

        with self._lock:
            entry = self._store.get(key)

            if entry is None:
                self.misses += 1
                return None

            if entry.expires_at <= time.monotonic():
                self._store.pop(key, None)
                self.misses += 1
                return None

            self.hits += 1
            return entry.value

    def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None,
    ) -> None:
        """
        Store a value with an optional per-entry TTL.

        When the cache reaches its maximum size, the entries closest to
        expiration are removed first.
        """

        ttl_seconds = (
            self._default_ttl
            if ttl is None
            else max(0, int(ttl))
        )

        with self._lock:
            if key not in self._store and len(self._store) >= self._max_entries:
                self._evict_oldest_locked()

            self._store[key] = _Entry(
                value=value,
                expires_at=time.monotonic() + ttl_seconds,
            )

    def delete(self, key: str) -> None:
        """Remove one cache entry if it exists."""

        with self._lock:
            self._store.pop(key, None)

    def clear(self) -> None:
        """Remove every entry from the cache."""

        with self._lock:
            self._store.clear()

    def _evict_oldest_locked(self, count: int = 50) -> None:
        """
        Remove entries that expire soonest.

        This is intentionally simple because the configured caches are small.
        """

        if not self._store:
            return

        remove_count = min(count, len(self._store))

        oldest = sorted(
            self._store.items(),
            key=lambda item: item[1].expires_at,
        )[:remove_count]

        for key, _entry in oldest:
            self._store.pop(key, None)

    def stats(self) -> dict[str, Any]:
        """Return cache usage statistics."""

        with self._lock:
            total = self.hits + self.misses

            return {
                "entries": len(self._store),
                "hits": self.hits,
                "misses": self.misses,
                "hit_rate": (
                    round(self.hits / total, 3)
                    if total
                    else 0.0
                ),
                "ttlSeconds": self._default_ttl,
                "maxEntries": self._max_entries,
            }


# ---------------------------------------------------------------------------
# Cache-key normalization
# ---------------------------------------------------------------------------

_WHITESPACE_RE = re.compile(r"\s+")


def normalize_for_cache(text: str) -> str:
    """
    Normalize text conservatively for cache-key generation.

    Whitespace is collapsed and text is lowercased.

    Punctuation and wording are intentionally preserved so genuinely
    different claims are not accidentally merged into one cached result.
    """

    return _WHITESPACE_RE.sub(
        " ",
        (text or "").strip().lower(),
    )


# ---------------------------------------------------------------------------
# Gemini cache key
# ---------------------------------------------------------------------------

def make_gemini_cache_key(
    headline: str,
    article_url: str,
    article_text: str,
) -> str:
    """
    Create a stable cache key for Gemini news verification.

    Only the first 4,000 normalized article characters are included in the
    hash to prevent very large articles from unnecessarily increasing the
    hashing workload.
    """

    normalized = "|".join(
        [
            normalize_for_cache(headline),
            normalize_for_cache(article_url),
            normalize_for_cache(article_text)[:4000],
        ]
    )

    digest = hashlib.sha256(
        normalized.encode("utf-8")
    ).hexdigest()

    return f"gemini:news:{digest}"


# ---------------------------------------------------------------------------
# Search-result cache key
# ---------------------------------------------------------------------------

def make_search_cache_key(
    query: str,
    max_results: int,
) -> str:
    """
    Create a stable cache key for a search query.

    max_results is included because requesting 5 results and requesting
    20 results should not share the same cached response.
    """

    normalized_query = normalize_for_cache(query)

    raw = f"{normalized_query}|{int(max_results)}"

    digest = hashlib.sha256(
        raw.encode("utf-8")
    ).hexdigest()

    return f"search:{digest}"


# ---------------------------------------------------------------------------
# Article-content cache key
# ---------------------------------------------------------------------------

def make_article_cache_key(url: str) -> str:
    """Create a stable cache key for extracted article content."""

    normalized_url = normalize_for_cache(url)

    digest = hashlib.sha256(
        normalized_url.encode("utf-8")
    ).hexdigest()

    return f"article:{digest}"


# ---------------------------------------------------------------------------
# Named cache instances
# ---------------------------------------------------------------------------

# Gemini verification must remain relatively fresh because its purpose is
# current web verification.
gemini_news_cache = TTLCache(
    default_ttl=GEMINI_CACHE_TTL_SECONDS,
    max_entries=GEMINI_CACHE_MAX_ENTRIES,
)


# Search results can be reused briefly to avoid repeatedly querying external
# search providers for identical claims.
search_results_cache = TTLCache(
    default_ttl=SEARCH_CACHE_TTL_SECONDS,
    max_entries=SEARCH_CACHE_MAX_ENTRIES,
)


# Article content generally changes less often than search results, so it can
# safely use a longer TTL.
article_cache = TTLCache(
    default_ttl=ARTICLE_CACHE_TTL_SECONDS,
    max_entries=ARTICLE_CACHE_MAX_ENTRIES,
)


# ---------------------------------------------------------------------------
# Combined cache statistics
# ---------------------------------------------------------------------------

def cache_stats_all() -> dict[str, Any]:
    """
    Return statistics for all TrustGuard caches.

    This is suitable for exposing through a diagnostic endpoint such as
    GET /cache/stats.
    """

    return {
        "geminiNewsCache": gemini_news_cache.stats(),
        "searchResultsCache": search_results_cache.stats(),
        "articleCache": article_cache.stats(),
    }