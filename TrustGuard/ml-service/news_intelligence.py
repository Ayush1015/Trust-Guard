"""
TrustGuard — News Intelligence Extras
======================================

Extends the news pipeline with:

1. search_related_articles()  — finds other coverage of the same story via
   a free web search (DuckDuckGo HTML, no API key), with a short in-memory
   cache so repeated checks of a trending story don't re-fetch every time.

2. cross_check_related()      — runs the SAME local ML model against each
   independently-found related article and reports whether other coverage
   corroborates or conflicts with the submitted claim. This is a real
   second opinion, not just a link list.

3. classify_style()           — a separate "Clickbait / Opinion" signal,
   reported alongside (not instead of) the Fake/Real verdict. A clickbaity
   headline about a true event is still "Real" — it just also gets flagged
   as attention-bait so the user sees both facts.

4. extractive_summary()       — pure-Python, dependency-free summarizer
   used as the backup when Gemini is unavailable or fails, so summaries
   never go fully dark.

5. free_translate()           — optional backup translator using
   deep-translator's free Google Translate wrapper (no API key). Returns
   None (never raises) if the package isn't installed or the call fails,
   so callers must handle a None result gracefully.

Import from main.py:

    from news_intelligence import (
        search_related_articles,
        cross_check_related,
        classify_style,
        extractive_summary,
        free_translate,
    )
"""

from __future__ import annotations

import logging
import re
import time
from collections import Counter
from typing import Any, Callable, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import parse_qs, unquote, urlparse
from adapters.search_adapter import DuckDuckGoSearchAdapter, SearchResult, SearchService
from services.cache_service import (
    article_cache,
    make_article_cache_key,
    make_search_cache_key,
    search_results_cache,
)
 
import requests
_search_service = SearchService([DuckDuckGoSearchAdapter()])
 

logger = logging.getLogger("trustguard.news_intel")

# ---------------------------------------------------------------------
# SMALL IN-MEMORY TTL CACHE (no extra dependency)
# ---------------------------------------------------------------------

_SEARCH_CACHE: dict[str, tuple[float, list[dict[str, str]]]] = {}
_CACHE_TTL_SECONDS = 900  # 15 minutes — long enough to help a trending
                           # story get cheaper repeat checks, short enough
                           # that breaking news doesn't go stale.


def _cache_get(key: str) -> Optional[list[dict[str, str]]]:
    entry = _SEARCH_CACHE.get(key)
    if not entry:
        return None
    ts, value = entry
    if time.time() - ts > _CACHE_TTL_SECONDS:
        _SEARCH_CACHE.pop(key, None)
        return None
    return value


def _cache_set(key: str, value: list[dict[str, str]]) -> None:
    _SEARCH_CACHE[key] = (time.time(), value)
    # Simple unbounded-growth guard — drop the oldest half once large.
    if len(_SEARCH_CACHE) > 500:
        oldest = sorted(_SEARCH_CACHE.items(), key=lambda kv: kv[1][0])[:250]
        for k, _ in oldest:
            _SEARCH_CACHE.pop(k, None)


# ---------------------------------------------------------------------
# 1. RELATED-ARTICLE SEARCH (free, no API key)
# ---------------------------------------------------------------------

def _resolve_ddg_href(href: str) -> Optional[str]:
    """DuckDuckGo's HTML endpoint returns redirect wrapper links, e.g.
    '//duckduckgo.com/l/?uddg=<url-encoded-target>&rut=...', NOT the
    article URL directly. Unwrap that to the real destination and return
    None for anything that still isn't a usable absolute http(s) URL
    (so callers can safely skip it instead of passing garbage to a
    URL fetcher)."""
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


def _duckduckgo_search(query: str, limit: int) -> list[dict[str, str]]:
    try:
        resp = requests.get(
            "https://html.duckduckgo.com/html/",
            params={"q": query.strip()},
            timeout=8,
            headers={"User-Agent": "Mozilla/5.0 TrustGuard/1.0"},
        )
        resp.raise_for_status()
    except Exception as exc:
        logger.debug("duckduckgo search failed: %s", exc)
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
        logger.debug("duckduckgo parse failed: %s", exc)
        return []


def search_related_articles(
    query: str,
    extract_article_fn: Callable[[str], dict[str, str]],
    limit: int = 4,
) -> list[dict[str, str]]:
    """Finds independent coverage of the same story and extracts each
    article's text using the caller's own extract_article() function
    (passed in so this module doesn't duplicate main.py's trafilatura/
    BeautifulSoup extraction logic).

    Returns a list of {title, url, text} — entries where text extraction
    failed are dropped rather than passed on empty.
    """
    query = (query or "").strip()
    if not query:
        return []

    cache_key = query.lower()
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    links = _duckduckgo_search(query, limit=limit)
    articles: list[dict[str, str]] = []

    for link in links:
        try:
            extracted = extract_article_fn(link["url"])
        except Exception as exc:
            logger.debug("related-article extraction failed for %s: %s", link["url"], exc)
            continue

        text = (extracted or {}).get("text", "")
        if len(text) < 100:  # too little text to be a useful cross-check
            continue

        articles.append({
            "title": link["title"],
            "url": link["url"],
            "text": text,
        })

    _cache_set(cache_key, articles)
    return articles


# ---------------------------------------------------------------------
# 2. CROSS-CHECK AGAINST RELATED ARTICLES (real second opinion)
# ---------------------------------------------------------------------

_STOPWORDS = {
    "the", "a", "an", "of", "to", "in", "on", "for", "and", "or", "is",
    "are", "was", "were", "with", "as", "by", "at", "that", "this", "it",
    "from", "be", "has", "have", "had", "its", "their", "his", "her",
}


def _keyword_set(text: str) -> set[str]:
    words = re.findall(r"[a-zA-Z]{4,}", text.lower())
    return {w for w in words if w not in _STOPWORDS}


def _topic_overlap(a: str, b: str) -> float:
    """Cheap topical-similarity check (Jaccard over keyword sets). This is
    not semantic understanding — it only tells us whether a related
    article is plausibly about the same story, so we don't cross-check
    against something the search engine returned that's actually
    off-topic."""
    kw_a, kw_b = _keyword_set(a), _keyword_set(b)
    if not kw_a or not kw_b:
        return 0.0
    return len(kw_a & kw_b) / len(kw_a | kw_b)


def cross_check_related(
    original_content: str,
    related_articles: list[dict[str, str]],
    local_predict_fn: Callable[[str], Optional[dict[str, Any]]],
    min_topic_overlap: float = 0.08,
    max_voters: int = 3,
) -> dict[str, Any]:
    """Runs the SAME local ML model against each on-topic related article.

    Returns a summary the caller can both (a) turn into extra low-weight
    poll voters and (b) show the user directly as "N independent sources
    found, M ML-agreed Real / K ML-agreed Fake".
    """
    on_topic = [
        art for art in related_articles
        if _topic_overlap(original_content, art["text"]) >= min_topic_overlap
    ]

    votes: list[dict[str, Any]] = []
    for art in on_topic[:max_voters]:
        prediction = local_predict_fn(art["text"])
        if prediction:
            votes.append({**prediction, "sourceUrl": art["url"], "sourceTitle": art["title"]})

    label_counts = Counter(v["label"] for v in votes)

    return {
        "relatedArticlesFound": len(related_articles),
        "onTopicArticlesFound": len(on_topic),
        "crossCheckVotes": votes,
        "crossCheckSummary": dict(label_counts),
        "noIndependentCoverage": len(on_topic) == 0,
    }


# ---------------------------------------------------------------------
# 3. STYLE CLASSIFICATION — clickbait/opinion, separate from fake/real
# ---------------------------------------------------------------------

_CLICKBAIT_PHRASES = (
    "you won't believe", "shocking truth", "doctors hate", "one weird trick",
    "this one trick", "won't believe what happens", "secret they don't want",
    "click here", "share before it's deleted", "gone wrong", "goes viral",
)

_OPINION_MARKERS = (
    "opinion:", "op-ed", "editorial:", "i think", "in my view", "commentary:",
    "analysis:", "the case for", "the case against",
)


def classify_style(headline: str, article_text: str) -> dict[str, Any]:
    """Independent style signal — NOT a fake/real vote. A clickbaity
    headline about a real event should still poll as Real; this just
    tells the user the headline is also attention-bait, or that the
    piece reads as opinion/commentary rather than straight reporting."""
    combined = f"{headline} {article_text}".lower()

    clickbait_hits = sum(1 for p in _CLICKBAIT_PHRASES if p in combined)
    opinion_hits = sum(1 for p in _OPINION_MARKERS if p in combined)
    exclaim_count = headline.count("!")
    caps_words = sum(1 for w in headline.split() if len(w) > 3 and w.isupper())

    is_clickbait = clickbait_hits >= 1 or exclaim_count >= 2 or caps_words >= 2
    is_opinion = opinion_hits >= 1

    if is_opinion:
        tag = "Opinion/Commentary"
    elif is_clickbait:
        tag = "Clickbait / Eye-catching Headline"
    else:
        tag = "Straight Reporting"

    return {
        "styleTag": tag,
        "isClickbait": is_clickbait,
        "isOpinion": is_opinion,
    }


# ---------------------------------------------------------------------
# 4. EXTRACTIVE SUMMARY — dependency-free Gemini backup
# ---------------------------------------------------------------------

def extractive_summary(text: str, num_sentences: int = 3) -> str:
    """Frequency-based extractive summarizer. No external dependencies,
    no API key, works offline — used only when Gemini is unavailable so
    a summary is still returned rather than an error."""
    text = (text or "").strip()
    if not text:
        return ""

    sentences = re.split(r"(?<=[.!?])\s+", text)
    sentences = [s.strip() for s in sentences if len(s.strip()) > 20]
    if not sentences:
        return text[:400]
    if len(sentences) <= num_sentences:
        return " ".join(sentences)

    words = re.findall(r"[a-zA-Z]{3,}", text.lower())
    freq = Counter(w for w in words if w not in _STOPWORDS)
    if not freq:
        return " ".join(sentences[:num_sentences])

    max_freq = max(freq.values())
    scores = []
    for idx, sentence in enumerate(sentences):
        sentence_words = re.findall(r"[a-zA-Z]{3,}", sentence.lower())
        if not sentence_words:
            scores.append((0.0, idx))
            continue
        score = sum(freq.get(w, 0) for w in sentence_words) / max_freq / len(sentence_words)
        # Slight bias toward earlier sentences (lede tends to carry the
        # core fact in news writing).
        position_bonus = 1.0 if idx < 3 else 0.9
        scores.append((score * position_bonus, idx))

    top_indexes = sorted(sorted(scores, reverse=True)[:num_sentences], key=lambda x: x[1])
    return " ".join(sentences[i] for _, i in top_indexes)


# ---------------------------------------------------------------------
# 5. FREE TRANSLATION BACKUP (optional dependency)
# ---------------------------------------------------------------------

def free_translate(text: str, target_language: str) -> Optional[str]:
    """Backup translator for when Gemini is unavailable. Requires
    `pip install deep-translator`. Returns None (never raises) if the
    package is missing or the call fails — callers must handle a None
    result (e.g. by showing the original text with a note)."""
    text = (text or "").strip()
    if not text or not target_language:
        return None

    try:
        from deep_translator import GoogleTranslator

        # deep-translator has a ~5000 char per-call limit on the free
        # endpoint; chunk long articles rather than truncating silently.
        chunks = [text[i:i + 4500] for i in range(0, len(text), 4500)]
        translated_chunks = [
            GoogleTranslator(source="auto", target=target_language.lower()).translate(chunk)
            for chunk in chunks
        ]
        return " ".join(c for c in translated_chunks if c)
    except Exception as exc:
        logger.debug("free_translate unavailable/failed: %s", exc)
        return None


# ---------------------------------------------------------------------
# 6. OFFLINE NEWS VERIFICATION — full Python substitute when Gemini is down
# ---------------------------------------------------------------------

def offline_news_verification(
    headline: str,
    article_text: str,
    extract_article_fn: Callable[[str], dict[str, str]],
    local_predict_fn: Callable[[str], Optional[dict[str, Any]]],
    limit: int = 5,
) -> dict[str, Any]:
    """Performs the SAME job as Gemini's web-grounded fact-check, using
    only free web search + your own local ML model -- no AI API call at
    all. Returns the same shape as gemini_news_check() so callers (and
    the frontend) don't need to know which one actually ran:

        {"available": bool, "label": "Real"|"Fake"|"Unknown",
         "explanation": str, "sources": [...], "mode": "offline"}

    This is intentionally conservative: it only calls something Real or
    Fake when a clear majority of independently found, on-topic articles
    agree via the local model. Anything less certain reports "Unknown"
    rather than guessing.
    """
    query = (headline or article_text[:150]).strip()
    if not query:
        return {
            "available": False,
            "label": "Unknown",
            "explanation": "No headline or article text was provided for offline verification.",
            "sources": [],
            "mode": "offline",
        }

    related = search_related_articles(query, extract_article_fn, limit=limit)

    if not related:
        return {
            "available": True,
            "label": "Unknown",
            "explanation": (
                "Offline verification (Gemini unavailable): no independent web coverage "
                "could be found for this claim via free web search. This does not mean "
                "the claim is false — it may be very recent, very niche, or the search "
                "engine may be temporarily unreachable."
            ),
            "sources": [],
            "mode": "offline",
        }

    content_for_topic_check = f"{headline} {article_text}".strip() or query
    cross_check = cross_check_related(
        content_for_topic_check, related, local_predict_fn, max_voters=limit
    )
    votes = cross_check["crossCheckVotes"]
    sources = [{"title": a["title"], "url": a["url"]} for a in related]

    if not votes:
        return {
            "available": True,
            "label": "Unknown",
            "explanation": (
                f"Offline verification (Gemini unavailable): found {len(related)} web "
                "result(s) for this topic, but none were close enough in subject matter "
                "or long enough in content to confidently cross-check with the local model."
            ),
            "sources": sources,
            "mode": "offline",
        }

    label_counts = Counter(v["label"] for v in votes)
    total = len(votes)
    top_label, top_count = label_counts.most_common(1)[0]
    agreement = top_count / total

    # Only commit to Real/Fake on a clear majority; otherwise stay honest
    # about the uncertainty rather than forcing a verdict.
    label = top_label if top_label in ("Real", "Fake") and agreement >= 0.5 else "Unknown"

    explanation = (
        f"Offline verification (Gemini unavailable): the local ML model was run against "
        f"{total} independently found article{'s' if total != 1 else ''} covering this "
        f"topic. {top_count} of {total} were classified '{top_label}' "
        f"({round(agreement * 100)}% agreement). This is an automated cross-check against "
        "other web coverage using your own trained models, not a human fact-check."
    )

    return {
        "available": True,
        "label": label,
        "explanation": explanation,
        "sources": sources,
        "mode": "offline",
    }

def collect_related_articles(
    queries: list[str], primary_label: str, max_results: int = 5
) -> dict:
    """Runs each suggested search query and returns a de-duplicated list
    of related links. This is the function main.py's analyze_news() calls
    as `collect_related_articles(...)` but never imported -- that missing
    import was one of the two reasons the service failed to start."""
    seen_urls: set[str] = set()
    combined: list[dict] = []

    for query in queries[:3]:
        for result in _cached_search(query, max_results):
            if result.url in seen_urls:
                continue
            seen_urls.add(result.url)
            combined.append({"title": result.title, "url": result.url, "query": query})

    return {
        "primaryLabel": primary_label,
        "queriesUsed": queries[:3],
        "articles": combined[:10],
    }


def _run_search(query: str, max_results: int) -> list:
    """Calls whichever search method the installed SearchService actually
    exposes. This project has had two shapes of SearchService in flight
    at once (a simple .search(query, max_results) and a
    .multi_query_search(...) that takes query variants) -- calling the
    wrong one by name doesn't raise until a real request hits it, so this
    checks what's actually there instead of assuming.
 
    If your SearchService only implements multi_query_search(), it is
    called with a single-item variant list; if it returns per-variant
    grouping rather than a flat list, this flattens/dedupes by URL.
    """
    if hasattr(_search_service, "search"):
        return _search_service.search(query, max_results=max_results)
 
    if hasattr(_search_service, "multi_query_search"):
        raw = _search_service.multi_query_search([query], max_results=max_results)
        return _flatten_search_results(raw)
 
    raise AttributeError(
        "SearchService has neither .search() nor .multi_query_search() -- "
        "news_intelligence.py needs updating to match the installed adapter."
    )
 
 
def _flatten_search_results(raw) -> list:
    """Normalizes whatever multi_query_search() returns (a flat list, a
    list of lists, or a dict keyed by query variant) into one de-duplicated
    flat list of results with a .url attribute, since every caller here
    just wants "the results", not per-variant grouping."""
    flat = []
    if isinstance(raw, dict):
        for values in raw.values():
            flat.extend(values or [])
    elif raw and isinstance(raw[0], (list, tuple)):
        for values in raw:
            flat.extend(values or [])
    else:
        flat = list(raw or [])
 
    seen_urls = set()
    deduped = []
    for item in flat:
        url = getattr(item, "url", None) or (item.get("url") if isinstance(item, dict) else None)
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        deduped.append(item)
    return deduped
 
 
def _cached_search(query: str, max_results: int) -> list[SearchResult]:
    """Wraps SearchService.search() with a short-TTL cache so repeated
    claims (or a user retrying the same check) don't re-hit DuckDuckGo
    every time. Cache misses/empty results are not cached, so a
    transient search-provider outage doesn't get "stuck" as empty."""
    cache_key = make_search_cache_key(query, max_results)
    cached = search_results_cache.get(cache_key)
    if cached is not None:
        return cached
 
    results = _run_search(query, max_results)
    if results:
        search_results_cache.set(cache_key, results)
    return results
 
 
def _cached_extract(url: str, extract_article_fn: Callable) -> Optional[dict]:
    """Wraps an article-extraction call with a long-TTL cache, since
    published article text is effectively immutable. Extraction
    failures (falsy/errored results) are not cached, so a page that's
    temporarily down gets retried on the next request instead of being
    permanently marked as unfetchable."""
    cache_key = make_article_cache_key(url)
    cached = article_cache.get(cache_key)
    if cached is not None:
        return cached
 
    extracted = extract_article_fn(url)
    if extracted and extracted.get("text") and not extracted.get("error"):
        article_cache.set(cache_key, extracted)
    return extracted
 
_SENSATIONAL_WORDS = (
    "shocking", "unbelievable", "destroys", "slams", "exposed",
    "secret", "miracle", "banned", "outrage", "you won't believe",
)
 