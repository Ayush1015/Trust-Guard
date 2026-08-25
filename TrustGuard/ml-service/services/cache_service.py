"""
§35: Caching.

In-memory, TTL-based, thread-safe-enough for a single uvicorn worker
(a dict + a lock). This is explicitly a stand-in for Redis — the
interface (get/set/make_key) is small on purpose so swapping the
backend later doesn't touch any caller.

Short TTL by design: Gemini's job here is CURRENT web verification.
Caching it for hours would silently make "current" claims stale,
which is the exact failure mode §5 exists to catch. Default TTL is
tuned for "protects against duplicate requests and burst dev testing,"
not "reduces API calls under real traffic" — raise CACHE_TTL_SECONDS
deliberately, with that tradeoff in mind, rather than by default.
"""

from __future__ import annotations

import hashlib
import re
import threading
import time
from dataclasses import dataclass
from typing import Any, Optional

DEFAULT_TTL_SECONDS = 300  # 5 minutes


@dataclass
class _Entry:
    value: Any
    expires_at: float



class TTLCache:
    def __init__(self, default_ttl: int = DEFAULT_TTL_SECONDS, max_entries: int = 500):
        self._store: dict[str, _Entry] = {}
        self._lock = threading.Lock()
        self._default_ttl = default_ttl
        self._max_entries = max_entries
        self.hits = 0
        self.misses = 0

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                self.misses += 1
                return None
            if entry.expires_at < time.monotonic():
                del self._store[key]
                self.misses += 1
                return None
            self.hits += 1
            return entry.value

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        with self._lock:
            if len(self._store) >= self._max_entries:
                self._evict_oldest_locked()
            self._store[key] = _Entry(
                value=value,
                expires_at=time.monotonic() + (ttl if ttl is not None else self._default_ttl),
            )


    def _evict_oldest_locked(self, count: int = 50) -> None:
        # Cheapest correct eviction for a dict this small; swap for an
        # OrderedDict/LRU if entry counts grow much past a few thousand.
        oldest = sorted(self._store.items(), key=lambda kv: kv[1].expires_at)[:count]
        for key, _ in oldest:
            self._store.pop(key, None)

    def stats(self) -> dict:
        with self._lock:
            return {
                "entries": len(self._store),
                "hits": self.hits,
                "misses": self.misses,
                "hit_rate": round(self.hits / (self.hits + self.misses), 3) if (self.hits + self.misses) else 0.0,
            }


_WHITESPACE_RE = re.compile(r"\s+")


def normalize_for_cache(text: str) -> str:
    """Collapses whitespace and lowercases so 'India Raises Sugar Prices'
    and 'india  raises sugar prices' hit the same cache entry. Does NOT
    touch punctuation/wording — this is intentionally conservative to
    avoid merging genuinely different claims into one cached verdict."""
    return _WHITESPACE_RE.sub(" ", (text or "").strip().lower())


def make_gemini_cache_key(headline: str, article_url: str, article_text: str) -> str:
    normalized = "|".join([
        normalize_for_cache(headline),

        normalize_for_cache(article_url),
        normalize_for_cache(article_text)[:4000],  # cap: full articles shouldn't dominate hashing cost
    ])
    return "gemini:news:" + hashlib.sha256(normalized.encode("utf-8")).hexdigest()


# Module-level singleton — one cache per process, same pattern as the
# existing MODEL_ERRORS/MODEL_LOAD_EVENTS globals in main.py.
gemini_news_cache = TTLCache(default_ttl=DEFAULT_TTL_SECONDS)