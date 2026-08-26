"""
TrustGuard — Reliability Extras
================================

Adds always-available, zero-dependency "3rd/4th voter" heuristics so every
module (news / review / phishing) keeps a multi-model ensemble even when
Kaggle pretrained downloads fail or BERTPhish/Gemini are unavailable.

Also adds the "standard checklist" phishing signals: typosquatting,
redirect-chain inspection, and (optional) WHOIS domain age.

Import this from main.py:

    from trust_extras import (
        heuristic_news_vote,
        heuristic_review_vote,
        heuristic_phishing_vote,
        duckduckgo_related,
        domain_age_days,
    )
"""

from __future__ import annotations

import difflib
import logging
import re
from typing import Any, Optional
from urllib.parse import parse_qs, unquote, urlparse

import requests

logger = logging.getLogger("trustguard.extras")

# ---------------------------------------------------------------------
# NEWS — heuristic stylometric voter
# ---------------------------------------------------------------------

_CLICKBAIT_MARKERS = (
    "you won't believe", "shocking truth", "!!!", "miracle cure",
    "doctors hate", "secret they don't want", "click here",
    "won't believe what happens", "this one trick", "share before it's deleted",
)


def heuristic_news_vote(headline: str, article_text: str, make_prediction):
    """Cheap stylometric heuristic. Always available, no external calls.

    Parameters
    ----------
    headline : str
    article_text : str
    make_prediction : callable
        The make_prediction(name, label, confidence, source=..., weight=...)
        helper already defined in main.py, passed in so this module doesn't
        need to duplicate that helper's exact schema.
    """
    content = f"{headline} {article_text}".lower()
    marker_hits = sum(1 for m in _CLICKBAIT_MARKERS if m in content)

    words = f"{headline} {article_text}".split()
    shouting_words = sum(1 for w in words if len(w) > 3 and w.isupper())
    exclaim_density = content.count("!") / max(len(content), 1)

    red_flags = marker_hits + (1 if shouting_words > 5 else 0) + (1 if exclaim_density > 0.01 else 0)

    if red_flags >= 2:
        return make_prediction("Heuristic Style Check", "Fake", 0.55, source="heuristic", weight=0.5)
    return make_prediction("Heuristic Style Check", "Real", 0.55, source="heuristic", weight=0.5)


# ---------------------------------------------------------------------
# REVIEW — heuristic spam-pattern voter
# ---------------------------------------------------------------------

_REVIEW_SPAM_PHRASES = (
    "best product ever", "buy now", "highly recommend!!!",
    "changed my life", "5 stars!!!", "amazing amazing amazing",
)


def heuristic_review_vote(text: str, make_prediction):
    """Cheap spam-pattern heuristic for reviews. Always available.

    Parameters
    ----------
    text : str
    make_prediction : callable
        Same make_prediction helper from main.py.
    """
    content = text.lower()
    exclaim = content.count("!")
    superlatives = sum(1 for w in ("amazing", "perfect", "incredible", "best ever", "flawless") if w in content)
    phrase_hits = sum(1 for p in _REVIEW_SPAM_PHRASES if p in content)
    repeated_words = len(re.findall(r"\b(\w+)\b(?:\W+\1\b)+", content, flags=re.I))

    red_flags = phrase_hits + repeated_words + (1 if exclaim >= 4 else 0) + (1 if superlatives >= 2 else 0)

    if red_flags >= 2:
        return make_prediction("Heuristic Spam Pattern", "Fake", 0.5, source="heuristic", weight=0.5)
    return make_prediction("Heuristic Spam Pattern", "Genuine", 0.5, source="heuristic", weight=0.5)


# ---------------------------------------------------------------------
# PHISHING — standard checklist (typosquat / redirect chain / SSL / TLD)
# ---------------------------------------------------------------------

POPULAR_DOMAINS = (
    "google.com", "paypal.com", "amazon.com", "microsoft.com", "apple.com",
    "facebook.com", "instagram.com", "netflix.com", "bankofamerica.com",
    "chase.com", "irs.gov", "wellsfargo.com", "linkedin.com", "dropbox.com",
)


def typosquat_check(hostname: str) -> Optional[str]:
    """Returns the popular domain this hostname closely resembles, or None."""
    if not hostname:
        return None
    if hostname in POPULAR_DOMAINS:
        return None  # exact match is the real thing, not a typosquat
    best_match, best_ratio = None, 0.0
    for domain in POPULAR_DOMAINS:
        ratio = difflib.SequenceMatcher(None, hostname, domain).ratio()
        if ratio > best_ratio:
            best_ratio, best_match = ratio, domain
    # Similar enough to be confusing, but not identical.
    if 0.75 <= best_ratio < 1.0:
        return best_match
    return None


def redirect_chain_check(url: str, timeout: int = 8) -> dict[str, Any]:
    """Follows redirects and flags long/suspicious redirect chains.
    Fails safe (non-suspicious) on any network error."""
    try:
        resp = requests.head(
            url, timeout=timeout, allow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 TrustGuard/1.0"},
        )
        hops = len(resp.history)
        final_host = urlparse(resp.url).hostname
        return {
            "hops": hops,
            "finalHost": final_host,
            "suspicious": hops >= 3,
            "checked": True,
        }
    except Exception as exc:
        logger.debug("redirect_chain_check failed for %s: %s", url, exc)
        return {"hops": 0, "finalHost": None, "suspicious": False, "checked": False}


def domain_age_days(hostname: str) -> Optional[int]:
    """Optional WHOIS lookup. Requires `pip install python-whois`.
    Returns None (never raises) if the library isn't installed or the
    lookup fails/times out — the phishing pipeline must keep working
    without it."""
    try:
        import whois  # python-whois
        from datetime import datetime

        result = whois.whois(hostname)
        created = result.creation_date
        if isinstance(created, list):
            created = created[0]
        if not created:
            return None
        return (datetime.now() - created).days
    except Exception as exc:
        logger.debug("domain_age_days unavailable for %s: %s", hostname, exc)
        return None


def heuristic_phishing_vote(url: str, hostname: str, ssl_ok: bool, shady_tld: bool, make_prediction):
    """Combines typosquat + redirect-chain + SSL + TLD into one voter,
    and returns the raw sub-signals so the API response can surface them
    to the user (the "standard checklist" the user asked for).

    Parameters
    ----------
    url : str
    hostname : str
    ssl_ok : bool
    shady_tld : bool
    make_prediction : callable
        Same make_prediction helper from main.py.

    Returns
    -------
    (vote_dict, checklist_dict)
    """
    typosquat_target = typosquat_check(hostname)
    redirects = redirect_chain_check(url)

    red_flags = 0
    if typosquat_target:
        red_flags += 2
    if redirects["suspicious"]:
        red_flags += 1
    if not ssl_ok:
        red_flags += 1
    if shady_tld:
        red_flags += 1

    label = "Phishing" if red_flags >= 2 else "Safe"
    vote = make_prediction(
        "Standard Checklist (typosquat / redirects / SSL / TLD)",
        label,
        0.6,
        source="heuristic",
        weight=0.75,
    )

    checklist = {
        "typosquattingOf": typosquat_target,
        "redirectHops": redirects["hops"],
        "finalDestination": redirects["finalHost"],
        "redirectCheckAvailable": redirects["checked"],
    }

    return vote, checklist


# ---------------------------------------------------------------------
# NEWS — free related-article search fallback (no API key required)
# ---------------------------------------------------------------------

def _resolve_ddg_href(href: str) -> Optional[str]:
    """DuckDuckGo's HTML endpoint returns redirect wrapper links, e.g.
    '//duckduckgo.com/l/?uddg=<url-encoded-target>&rut=...', NOT the
    article URL directly. Unwrap that to the real destination and return
    None for anything that still isn't a usable absolute http(s) URL."""
    href = (href or "").strip()
    if not href:
        return None

    if href.startswith("//"):
        href = "https:" + href
    elif href.startswith("/"):
        href = "https://duckduckgo.com" + href

    parsed = urlparse(href)

    if "duckduckgo.com" in (parsed.hostname or "") and parsed.path.startswith("/l/"):
        target = parse_qs(parsed.query).get("uddg", [None])[0]
        if not target:
            return None
        href = unquote(target)
        parsed = urlparse(href)

    if parsed.scheme in ("http", "https") and parsed.hostname:
        return href
    return None


def duckduckgo_related(query: str, limit: int = 5) -> list[dict[str, str]]:
    """Used only when Gemini is not configured / returned no sources, so
    'related news' still works for every user, not just ones with a key."""
    if not query or not query.strip():
        return []
    try:
        resp = requests.get(
            "https://html.duckduckgo.com/html/",
            params={"q": query.strip()},
            timeout=8,
            headers={"User-Agent": "Mozilla/5.0 TrustGuard/1.0"},
        )
        resp.raise_for_status()
    except Exception as exc:
        logger.debug("duckduckgo_related failed: %s", exc)
        return []

    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(resp.text, "html.parser")
        results = []
        for a in soup.select(".result__a"):
            if len(results) >= limit:
                break
            title = a.get_text(strip=True)
            resolved_url = _resolve_ddg_href(a.get("href", ""))
            if title and resolved_url:
                results.append({"title": title, "url": resolved_url})
        return results
    except Exception as exc:
        logger.debug("duckduckgo_related parse failed: %s", exc)
        return []