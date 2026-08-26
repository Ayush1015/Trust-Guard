"""
TrustGuard — Gemini Quota Backup
==================================

Provides a small in-memory key-rotation pool so a single exhausted Gemini
API key doesn't take down news verification/summary/translation. If you
configure more than one free-tier key (GEMINI_API_KEYS=key1,key2,key3),
this automatically rotates to the next available key when one returns a
429/RESOURCE_EXHAUSTED error, and puts the exhausted key on a cooldown
before trying it again.

This does NOT bypass Google's rate limits or terms of service — it only
helps you use multiple keys you legitimately own (e.g. separate free-tier
projects) without manually swapping them when one runs out.

Usage in main.py:

    from gemini_backup import GeminiKeyRotator, is_quota_error

    GEMINI_KEYS = [k.strip() for k in os.getenv("GEMINI_API_KEYS", "").split(",") if k.strip()] \\
                  or ([GEMINI_API_KEY] if GEMINI_API_KEY else [])
    gemini_rotator = GeminiKeyRotator(GEMINI_KEYS)

    # when calling Gemini:
    key = gemini_rotator.get_key()
    try:
        ... call Gemini with `key` ...
    except Exception as exc:
        if is_quota_error(exc):
            gemini_rotator.mark_exhausted(key)
            # retry with gemini_rotator.get_key() again, up to len(keys) times
        else:
            raise
"""

from __future__ import annotations

import time
from typing import Optional


def is_quota_error(exc: Exception) -> bool:
    """Detects a 429/RESOURCE_EXHAUSTED error from the google-genai SDK
    without importing its specific exception types (which have changed
    across SDK versions). Matches on the error text, which has been
    stable: '429 RESOURCE_EXHAUSTED' / 'quota'."""
    text = str(exc).lower()
    return "429" in text or "resource_exhausted" in text or "quota" in text


class GeminiKeyRotator:
    """Round-robin pool of Gemini API keys with a per-key cooldown after
    a quota error. Thread-safety note: FastAPI's default sync endpoints
    run in a threadpool, so this uses simple operations that are safe
    enough for the low contention here (worst case is an extra retry,
    never a crash)."""

    def __init__(self, keys: list[str], cooldown_seconds: int = 90):
        # De-duplicate while preserving order, drop blanks.
        seen = set()
        self.keys: list[str] = []
        for k in keys:
            k = (k or "").strip()
            if k and k not in seen:
                seen.add(k)
                self.keys.append(k)

        self.cooldown_seconds = cooldown_seconds
        self._exhausted_until: dict[str, float] = {}
        self._index = 0

    def has_keys(self) -> bool:
        return len(self.keys) > 0

    def get_key(self) -> Optional[str]:
        """Returns the next available (non-cooling-down) key, or None if
        every configured key is currently exhausted."""
        now = time.time()
        n = len(self.keys)
        if n == 0:
            return None

        for i in range(n):
            idx = (self._index + i) % n
            key = self.keys[idx]
            if self._exhausted_until.get(key, 0) <= now:
                self._index = (idx + 1) % n
                return key

        return None

    def mark_exhausted(self, key: Optional[str]) -> None:
        if key:
            self._exhausted_until[key] = time.time() + self.cooldown_seconds

    def status(self) -> dict:
        now = time.time()
        available = sum(1 for k in self.keys if self._exhausted_until.get(k, 0) <= now)
        return {
            "totalKeys": len(self.keys),
            "availableKeys": available,
            "allExhausted": len(self.keys) > 0 and available == 0,
        }
