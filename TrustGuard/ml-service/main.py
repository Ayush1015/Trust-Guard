"""
TrustGuard ML Service
FastAPI ensemble service for news, reviews and phishing.

Run:
    python main.py

Expected:
    ml-service/
      main.py
      trust_extras.py
      .env
      models/
      pretrained_models/
        model_paths.json   # optional
"""

from __future__ import annotations

import ipaddress
import json
import logging
import os
import re
from collections import Counter
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Optional
from urllib.parse import parse_qs, unquote, urlparse

import joblib
import numpy as np
import requests
import hashlib
import time
import uuid
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed

from bs4 import BeautifulSoup 
from adapters.search_adapter import DuckDuckGoSearchAdapter, SearchService, SearchResult
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from services.safe_fetch import safe_fetch_html
from trust_extras import (
    heuristic_news_vote,
    heuristic_review_vote,
    heuristic_phishing_vote,
    duckduckgo_related,
    domain_age_days,
)
from news_intelligence import (
    search_related_articles,
    cross_check_related,
    classify_style,
    extractive_summary,
    free_translate,
    offline_news_verification,
    collect_related_articles,
)
from gemini_backup import GeminiKeyRotator, is_quota_error
from adapters.model_registry import ModelAdapter, ModelRegistry
from services.claim_service import build_structured_claim, claim_to_search_queries
from services.temporal_service import classify_currentness
from services.synthesis_service import synthesize
from services.cache_service import gemini_news_cache, make_gemini_cache_key
from services.clustering_service import (
    ArticleForClustering,
    cluster_articles,
    independence_summary,
)
from difflib import SequenceMatcher
from time import time as _now


SEARCH_ENGINE_URL = "https://html.duckduckgo.com/html/"

BASE_DIR = Path(__file__).resolve().parent
_PIB_CACHE: dict[str, tuple[float, dict]] = {}
PIB_CACHE_TTL = 900 

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("trustguard")


def env_int(name: str, default: int, *, minimum: int | None = None) -> int:
    """Read an integer environment variable without crashing startup."""
    raw = os.getenv(name)
    try:
        value = int(raw) if raw is not None else default
    except (TypeError, ValueError):
        logger.warning("[CONFIG] Invalid integer for %s=%r; using %s", name, raw, default)
        value = default
    if minimum is not None and value < minimum:
        logger.warning("[CONFIG] %s=%s is below minimum %s; using %s", name, value, minimum, minimum)
        value = minimum
    return value


def load_env_file_safely(path: Path) -> None:
    """
    Load simple KEY=VALUE .env entries without python-dotenv's parser.
    This prevents one malformed line from producing a startup warning or
    stopping the rest of the configuration from loading.
    Existing OS environment variables always win.
    """
    if not path.exists():
        return

    try:
        for raw in path.read_text(encoding="utf-8-sig").splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[7:].lstrip()

            if "=" not in line:
                logger.warning("[ENV] Ignoring malformed .env line: %s", raw)
                continue

            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip()

            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
                logger.warning("[ENV] Ignoring invalid .env key: %s", key)
                continue

            # Remove matching single/double quotes.
            if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
                value = value[1:-1]

            # Support an inline comment only when it is separated by whitespace.
            value = re.sub(r"\s+#.*$", "", value).strip()

            os.environ.setdefault(key, value)
    except Exception as exc:
        logger.warning("[ENV] Could not read %s: %s", path, exc)


load_env_file_safely(BASE_DIR / ".env")

HOST = os.getenv("HOST", "127.0.0.1")
PORT = env_int("PORT", 8000, minimum=1)
RELOAD = os.getenv("RELOAD", "true").strip().lower() in {"1", "true", "yes", "on"}

# ---------------------------------------------------------------------
# TIMEOUT CONFIGURATION
# ---------------------------------------------------------------------
# A full /analyze/news run can chain many outbound network calls (article
# extraction, PIB search + page fetches, DuckDuckGo search, related-article
# fetches, Gemini). Each one used to carry its own small, independently
# guessed timeout (some as low as 8s), which meant the SLOWEST call in the
# chain -- not the total analysis time -- decided whether the whole request
# failed. Timeouts are now centralized here, sized generously by default,
# and fully configurable via environment variables so a slow network never
# has to mean a broken feature. Every outbound HTTP call in this file uses
# one of these constants (or REQUEST_TIMEOUT itself) instead of a
# hard-coded number.
REQUEST_TIMEOUT = env_int("REQUEST_TIMEOUT", 45, minimum=5)
PIB_SEARCH_TIMEOUT = env_int("PIB_SEARCH_TIMEOUT", REQUEST_TIMEOUT, minimum=5)
PIB_PAGE_FETCH_TIMEOUT = env_int("PIB_PAGE_FETCH_TIMEOUT", REQUEST_TIMEOUT, minimum=5)
PAGE_TITLE_FETCH_TIMEOUT = env_int("PAGE_TITLE_FETCH_TIMEOUT", 15, minimum=5)
SEARCH_ENGINE_TIMEOUT = env_int("SEARCH_ENGINE_TIMEOUT", REQUEST_TIMEOUT, minimum=5)
GEMINI_REQUEST_TIMEOUT = env_int("GEMINI_REQUEST_TIMEOUT", 90, minimum=10)

MAX_ARTICLE_CHARS = env_int("MAX_ARTICLE_CHARS", 30000, minimum=1000)
MAX_INPUT_CHARS = env_int("MAX_INPUT_CHARS", 100000, minimum=1000)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.6-flash").strip()

GEMINI_API_KEYS = (
    [k.strip() for k in os.getenv("GEMINI_API_KEYS", "").split(",") if k.strip()]
    or ([GEMINI_API_KEY] if GEMINI_API_KEY else [])
)
gemini_rotator = GeminiKeyRotator(GEMINI_API_KEYS, cooldown_seconds=90)

PIB_FACTCHECK_SEARCH_URL = "https://factcheck.pib.gov.in/search"
PIB_FACTCHECK_BASE = "https://factcheck.pib.gov.in"

STOPWORDS = {
    "the", "a", "an", "is", "are", "was", "were", "in", "on", "at", "of",
    "to", "for", "and", "or", "with", "by", "has", "have", "had", "this",
    "that", "it", "as", "be", "been", "will", "says", "said", "over",
}

TRUSTED_NEWS_DOMAINS = {
    "reuters.com", "apnews.com", "bbc.com", "bbc.co.uk", "npr.org",
    "theguardian.com", "nytimes.com", "washingtonpost.com", "wsj.com",
    "aljazeera.com", "hindustantimes.com", "thehindu.com", "indianexpress.com",
    "ndtv.com", "timesofindia.indiatimes.com", "pib.gov.in", "factcheck.pib.gov.in",
    "who.int", "cdc.gov", "un.org", "afp.com", "pti.in", "bloomberg.com",
    "cnn.com", "abcnews.go.com",
}

SHADY_NEWS_PATTERNS = ("blogspot", "wordpress.com/20", "wixsite", ".click", "viral")

# WHOIS domain-age lookups are a real network call with real latency, so
# they stay opt-in rather than firing on every phishing check by default.
ENABLE_DOMAIN_AGE_LOOKUP = os.getenv("ENABLE_DOMAIN_AGE_LOOKUP", "false").lower() == "true"
ENABLE_WEB_SEARCH_VERIFICATION = os.getenv("ENABLE_WEB_SEARCH_VERIFICATION", "false").lower() == "true"
MAX_SEARCH_ARTICLES_TO_FETCH = env_int("MAX_SEARCH_ARTICLES_TO_FETCH", 6, minimum=1)
SEARCH_FETCH_WORKERS = env_int("SEARCH_FETCH_WORKERS", 4, minimum=1)

_search_service = SearchService([DuckDuckGoSearchAdapter()])
CORS_ORIGINS = [
    x.strip()
    for x in os.getenv(
        "CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173",
    ).split(",")
    if x.strip()
]

# Optional explicit paths. If absent, the service auto-discovers the
# first directory containing the expected local model artifacts.
def choose_models_dir() -> Path:
    configured = os.getenv("MODELS_DIR", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()

    candidates = [
        BASE_DIR / "models",
        BASE_DIR.parent / "models",
        BASE_DIR.parent.parent / "models",
    ]
    required_groups = [
        {"news_model.joblib", "news_vectorizer.joblib"},
        {"review_model.joblib", "review_vectorizer.joblib"},
        {"local_phishing_model.joblib"},
        {"phishing_model.joblib"},
    ]

    best = candidates[0]
    best_score = -1
    for candidate in candidates:
        if not candidate.exists():
            continue
        names = {p.name for p in candidate.iterdir() if p.is_file()}
        score = sum(bool(group & names) for group in required_groups)
        if score > best_score:
            best_score = score
            best = candidate
    return best.resolve()

MODELS_DIR = choose_models_dir()

configured_pretrained = os.getenv("PRETRAINED_MODELS_DIR", "").strip()
PRETRAINED_DIR = (
    Path(configured_pretrained).expanduser().resolve()
    if configured_pretrained
    else (BASE_DIR / "pretrained_models").resolve()
)

try:
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    PRETRAINED_DIR.mkdir(parents=True, exist_ok=True)
except OSError as exc:
    raise RuntimeError(
        f"Unable to create model directories: {MODELS_DIR} / {PRETRAINED_DIR}"
    ) from exc


news_model: Any = None
news_vectorizer: Any = None
review_model: Any = None
review_vectorizer: Any = None
phishing_model: Any = None

# Every entry has:
# name, task, kind, model, optional vectorizer/scaler/feature_count
pretrained_models: list[dict[str, Any]] = []

bertphish_tokenizer: Any = None
bertphish_model: Any = None
gemini_client: Any = None

MODEL_ERRORS: list[str] = []
MODEL_LOAD_EVENTS: list[dict[str, Any]] = []
ENABLE_HF_NEWS_MODELS = os.getenv("ENABLE_HF_NEWS_MODELS", "true").lower() == "true"

# Hugging Face Hub IDs for general-purpose pretrained fake-news classifiers.
# These are the 4 concrete, loadable repos from the "Worldwide" shortlist —
# the Kaggle entries are training *datasets*, not inference-ready models,
# and the remaining India picks (HinFakeNews, Tamil MuRIL, multilingual
# MuRIL) were named without a public repo ID, so there's nothing to load
# yet. Add real IDs to HF_NEWS_MODELS (comma-separated) once you have them.
#
# IMPORTANT: verify each ID still exists on huggingface.co before relying
# on it — community repos get renamed, made private, or deleted. Any ID
# that fails to load is logged and skipped; it never enters the poll.
DEFAULT_HF_NEWS_MODELS = [
    "ThomasTschinkel/fake-news-detector",          # RoBERTa-Large
    "d-mistry013/fake-news-detector",              # RoBERTa-base
    "dhruvpal/fake-news-bert",                     # DistilBERT (lightweight)
    "akanbrown/AI-Fake_News_Detection_Roberta",    # RoBERTa, WELFake-based
]

HF_NEWS_MODEL_IDS = [
    x.strip()
    for x in os.getenv("HF_NEWS_MODELS", ",".join(DEFAULT_HF_NEWS_MODELS)).split(",")
    if x.strip()
]
hf_news_classifiers: list[dict[str, Any]] = []

@asynccontextmanager
async def lifespan(app: FastAPI):
    load_all_models()
    yield

app = FastAPI(
    title="TrustGuard ML Service",
    version="5.2.1",
    description="TrustGuard multi-model digital verification engine",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


class NewsPayload(BaseModel):
    text: str = Field(default="", max_length=100_000)
    headline: str = Field(default="", max_length=10_000)
    article_url: str = Field(default="", max_length=8_000)
    article_text: str = Field(default="", max_length=100_000)
    mode: str = Field(default="auto", max_length=20)

class TextPayload(BaseModel):
    text: str = Field(..., min_length=1, max_length=100_000)

class UrlPayload(BaseModel):
    url: str = Field(..., min_length=3, max_length=8_000)

class TranslationPayload(BaseModel):
    text: str = Field(..., min_length=1, max_length=50_000)
    language: str = Field(..., min_length=2, max_length=80)

class SummaryPayload(BaseModel):
    text: str = Field(..., min_length=1, max_length=50_000)
    language: str = Field(default="English", max_length=80)

class ReviewPagePayload(BaseModel):
    """Batch-analyze every review on a product page in one call, plus a
    simple rating-distribution check (e.g. suspicious 5-star pileups)."""
    reviews: list[str] = Field(default_factory=list, max_length=100)
    ratings: list[float] = Field(default_factory=list, max_length=100)

class ClaimPayload(BaseModel):
    headline: str = Field(default="", max_length=10_000)
    article_text: str = Field(default="", max_length=100_000)
class TemporalPayload(BaseModel):
    published_at: str = Field(default="")
    mentioned_dates: list[str] = Field(default_factory=list)

class ClusterArticleInput(BaseModel):
    id: str
    url: str
    domain: str = ""
    title: str = ""

class ClusterPayload(BaseModel):
    articles: list[ClusterArticleInput] = Field(default_factory=list)


news_registry = ModelRegistry()

def predict_pretrained_item(item: dict[str, Any], content: str):
    """Extracted from pretrained_text_predictions()'s loop body so a
    single item can be predicted on its own — needed by both the legacy
    poll path and the new per-model registry adapter, so there's still
    exactly one prediction implementation."""
    try:
        if item["kind"] == "pipeline":
            raw, conf = predict_model(item["model"], [content])
        elif item["kind"] == "tfidf":
            X = item["vectorizer"].transform([content])
            raw, conf = predict_model(item["model"], X)
        elif item["kind"] == "review_pipeline":
            vectorized = item["vectorizer"].transform([content])
            scaled = item["scaler"].transform(vectorized)
            raw, conf = predict_model(item["model"], scaled)
        else:
            return None
        if raw is None:
            return None
        label = news_label(raw) if item["task"] == "news" else review_label(raw)
        if label == "Unknown":
            return None
        return make_prediction(item["name"], label, conf, source="pretrained")
    except Exception as exc:
        logger.warning("[REGISTRY] %s failed: %s", item["name"], exc)
        return None

def build_news_registry():
    """Populate news_registry from whatever models are currently loaded.

    BUGFIX: this was previously defined but never called from anywhere,
    so news_registry stayed empty forever — /models/registry always
    reported zero adapters, and the per-article ML poll inside
    /analyze/news/stream silently did nothing. It is now invoked at the
    end of load_all_models(), after every model source has loaded.
    """
    news_registry.clear()

    if news_model is not None and news_vectorizer is not None:
        news_registry.register(ModelAdapter(
            name="Local News Model", task="news", version="tfidf-logreg",
            predict_fn=local_news_prediction,
        ))

    for item in [p for p in pretrained_models if p["task"] == "news"]:
        news_registry.register(ModelAdapter(
            name=item["name"], task="news", version=item.get("kind", "pretrained"),
            predict_fn=lambda content, _item=item: predict_pretrained_item(_item, content),
        ))

    for entry in hf_news_classifiers:
        news_registry.register(ModelAdapter(
            name=entry["name"], task="news", version=entry["repo_id"],
            predict_fn=lambda content, _entry=entry: hf_news_prediction(_entry, content),
        ))

    logger.info("[REGISTRY] news registry built: %d adapters", len(news_registry.for_task("news")))
def clean_text(value: Any) -> str:
    value = "" if value is None else str(value)
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()

def clamp01(value: Any, default: float = 0.5) -> float:
    try:
        x = float(value)
    except Exception:
        return default
    if x > 1.0:
        x /= 100.0
    return max(0.0, min(1.0, x))

def normalize_url(url: str) -> str:
    value = str(url or "").strip()
    if not value:
        return ""
    if not re.match(r"^https?://", value, re.I):
        value = "https://" + value
    return value

def validate_public_url(url: str):
    parsed = urlparse(normalize_url(url))
    if parsed.scheme.lower() not in {"http", "https"}:
        raise ValueError("Only HTTP and HTTPS URLs are supported.")

    hostname = (parsed.hostname or "").lower().rstrip(".")
    if not hostname:
        raise ValueError("The URL does not contain a hostname.")

    if hostname == "localhost" or hostname.endswith(".localhost"):
        raise ValueError("Localhost URLs are not supported.")

    try:
        ip = ipaddress.ip_address(hostname)
    except ValueError:
        ip = None

    if ip and (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
    ):
        raise ValueError("Private/local IP addresses are not supported.")

    if "." not in hostname and not ip:
        raise ValueError("A public domain name is required.")

    return parsed


def record_error(message: str):
    MODEL_ERRORS.append(message)
    logger.error(message)

def load_joblib(path: Path) -> Any:
    path = path.expanduser().resolve()
    logger.info("[MODEL] Looking for %s", path)

    if not path.exists():
        record_error(f"FILE NOT FOUND: {path}")
        return None

    if path.is_dir():
        record_error(f"EXPECTED FILE BUT GOT DIRECTORY: {path}")
        return None

    try:
        obj = joblib.load(path)
        details = {
            "file": str(path),
            "type": type(obj).__name__,
            "status": "loaded",
        }
        if hasattr(obj, "classes_"):
            details["classes"] = [str(x) for x in obj.classes_]
        if hasattr(obj, "n_features_in_"):
            details["features"] = int(obj.n_features_in_)
        MODEL_LOAD_EVENTS.append(details)

        logger.info(
            "[MODEL] Loaded %-35s type=%s",
            path.name,
            type(obj).__name__,
        )
        if hasattr(obj, "classes_"):
            logger.info("[MODEL] %s classes=%s", path.name, list(obj.classes_))
        if hasattr(obj, "n_features_in_"):
            logger.info(
                "[MODEL] %s features=%s",
                path.name,
                obj.n_features_in_,
            )
        return obj
    except Exception as exc:
        record_error(
            f"{path.name}: {type(exc).__name__}: {exc}"
        )
        logger.exception("[MODEL] Failed loading %s", path)
        return None


def _pib_cache_key(headline: str, article_text: str) -> str:
    basis = f"{headline.strip().lower()}|{article_text[:500].strip().lower()}"
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()


def pib_fact_check(headline: str, article_text: str) -> dict[str, Any]:
    """
    Search PIB for an existing fact-check and return a verdict only when
    the result is sufficiently relevant.

    Strategy:
    1. Search using the original headline.
    2. Search using distinctive keywords.
    3. Search using a shorter keyword query.
    4. Compare against PIB title AND page text.
    5. Prefer explicit PIB verdict markers.

    NOTE ON DUPLICATION FIX: this function used to be defined twice in
    this file. The second (later) definition silently shadowed this one
    — Python keeps only the last def with a given name — so the more
    thorough page-content-fetching version below was dead code and the
    service was actually running a title-only, single-query fallback.
    That duplicate has been removed; this is now the one and only
    implementation, and it is also cached (positive matches only —
    "not found"/"inconclusive" results are never cached, so a real PIB
    post published later is picked up on the next request rather than
    being masked by a stale miss).
    """
    cache_key = _pib_cache_key(headline, article_text)
    cached = _PIB_CACHE.get(cache_key)
    if cached is not None:
        cached_at, cached_result = cached
        if (_now() - cached_at) < PIB_CACHE_TTL:
            logger.info("[CACHE] PIB fact-check cache hit.")
            return cached_result
        _PIB_CACHE.pop(cache_key, None)

    query_source = (headline or "").strip() or (article_text or "")[:500].strip()

    if not query_source:
        return _pib_empty_result("No headline or text supplied.")

    keywords = extract_keywords(query_source, limit=10)

    queries = []
    if headline.strip():
        queries.append(headline.strip())

    if keywords:
        queries.append(" ".join(keywords[:8]))
        queries.append(" ".join(keywords[:5]))

    # Remove duplicate queries while preserving order.
    queries = list(dict.fromkeys(q for q in queries if q.strip()))

    all_posts = []

    for query in queries:
        try:
            posts = find_pib_posts(query, max_results=8)
            all_posts.extend(posts)
        except Exception as exc:
            logger.warning("[PIB] Search failed for %r: %s", query, exc)

    # Deduplicate PIB results by URL.
    unique_posts = []
    seen_urls = set()

    for post in all_posts:
        url = (post.get("url") or "").strip()

        if not url or url in seen_urls:
            continue

        if "pib.gov.in" not in url.lower() and "factcheck.pib.gov.in" not in url.lower():
            continue

        seen_urls.add(url)
        unique_posts.append(post)

    if not unique_posts:
        return _pib_empty_result(
            "No PIB fact-check posts found."
        )

    # Cheap title-only prefilter before paying for a full page fetch.
    # Fetching all 20 candidate pages serially (each up to REQUEST_TIMEOUT
    # seconds) could stall the whole /analyze/news request well past its
    # own budget. We now only fetch the most promising candidates, and do
    # so in parallel with a short, request-independent timeout.
    prefiltered = sorted(
        unique_posts[:20],
        key=lambda post: keyword_overlap_score(keywords, post.get("title", ""), query_source),
        reverse=True,
    )[:8]

    def _score_post(post: dict[str, str]) -> Optional[dict[str, Any]]:
        title = (post.get("title") or "").strip()
        url = (post.get("url") or "").strip()

        # Fetch the PIB page so matching is not based only on its title.
        page_text = ""
        try:
            response = requests.get(
                url,
                # Was hard-clamped to min(REQUEST_TIMEOUT, 8), which meant
                # PIB page fetches routinely timed out on slower connections
                # regardless of how generous REQUEST_TIMEOUT was configured.
                # Now uses its own configurable budget.
                timeout=PIB_PAGE_FETCH_TIMEOUT,
                headers={"User-Agent": "Mozilla/5.0 TrustGuard/1.0"},
            )

            if response.ok:
                soup = BeautifulSoup(response.text, "html.parser")

                # Remove scripts/styles before extracting text.
                for tag in soup(["script", "style", "noscript"]):
                    tag.decompose()

                page_text = soup.get_text(" ", strip=True)[:20000]

        except Exception as exc:
            logger.debug("[PIB] Could not fetch %s: %s", url, exc)

        combined = f"{title} {page_text}".strip()

        # Match against the whole PIB page, not just the title.
        score = keyword_overlap_score(keywords, combined, query_source)

        # Explicit PIB verdict should be detected from title + content.
        verdict = parse_pib_verdict(title, page_text)

        if not verdict:
            return None

        # Give explicit verdict-bearing PIB pages a small confidence bonus.
        score = min(1.0, score + 0.10)
        return {**post, "score": score, "verdict": verdict}

    scored = []
    with ThreadPoolExecutor(max_workers=min(4, len(prefiltered) or 1)) as executor:
        futures = [executor.submit(_score_post, post) for post in prefiltered]
        for future in as_completed(futures):
            try:
                result = future.result()
            except Exception as exc:
                logger.debug("[PIB] Scoring worker failed: %s", exc)
                continue
            if result:
                scored.append(result)

    if not scored:
        return _pib_empty_result(
            "PIB posts were found, but no explicit PIB verdict could be identified."
        )

    scored.sort(key=lambda x: x["score"], reverse=True)

    # Slightly lower than the old threshold because we now compare
    # against the complete PIB page rather than only its title.
    MATCH_THRESHOLD = 0.25

    strong_matches = [
        item for item in scored
        if item["score"] >= MATCH_THRESHOLD
    ]

    if not strong_matches:
        return _pib_empty_result(
            "PIB posts were found but none matched the supplied claim closely enough.",
            near_miss=scored[0],
        )

    # Use the strongest result as the primary fact-check.
    best = strong_matches[0]

    # Only accept additional matches when they agree.
    agreeing = [
        item for item in strong_matches[:5]
        if item["verdict"] == best["verdict"]
    ]

    result = {
        "available": True,
        "covered": True,
        "label": best["verdict"],
        "explanation": (
            f"PIB fact-check found. "
            f"Verdict: {best['verdict']}. "
            f"Matched {len(agreeing)} relevant PIB result(s)."
        ),
        "sources": [
            {
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "verdict": item.get("verdict"),
                "score": round(item.get("score", 0.0), 3),
            }
            for item in strong_matches[:5]
        ],
    }

    # Only cache real, positive coverage. Never cache "not found" or
    # "inconclusive" results, matching the project's "never cache
    # failures" caching policy — a fresh PIB post can appear at any time.
    _PIB_CACHE[cache_key] = (_now(), result)

    return result



def load_local_models():
    global news_model, news_vectorizer
    global review_model, review_vectorizer, phishing_model

    news_model = load_joblib(MODELS_DIR / "news_model.joblib")
    news_vectorizer = load_joblib(MODELS_DIR / "news_vectorizer.joblib")

    review_model = load_joblib(MODELS_DIR / "review_model.joblib")
    review_vectorizer = load_joblib(MODELS_DIR / "review_vectorizer.joblib")

    phishing_model = load_joblib(
        MODELS_DIR / "local_phishing_model.joblib"
    )
    if phishing_model is None:
        phishing_model = load_joblib(
            MODELS_DIR / "phishing_model.joblib"
        )

def read_model_paths() -> list[Path]:
    roots: list[Path] = [PRETRAINED_DIR]
    paths_file = PRETRAINED_DIR / "model_paths.json"

    if not paths_file.exists():
        return roots

    try:
        data = json.loads(paths_file.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("[PRETRAINED] Cannot read model_paths.json: %s", exc)
        return roots

    if isinstance(data, dict):
        values = list(data.values())
    elif isinstance(data, list):
        values = data
    else:
        values = []

    for value in values:
        if not isinstance(value, str) or not value.strip():
            continue
        path = Path(value).expanduser()
        if not path.is_absolute():
            path = (PRETRAINED_DIR / path).resolve()
        else:
            path = path.resolve()
        if path.exists():
            roots.append(path)
            logger.info("[PRETRAINED] Root discovered: %s", path)
        else:
            logger.warning("[PRETRAINED] Path does not exist: %s", path)

    return list(dict.fromkeys(roots))

def find_files(root: Path, suffixes=(".joblib", ".pkl", ".pickle")) -> list[Path]:
    if not root.exists():
        return []
    if root.is_file():
        return [root] if root.suffix.lower() in suffixes else []

    result = []
    try:
        for p in root.rglob("*"):
            if not p.is_file() or p.suffix.lower() not in suffixes:
                continue

            # BERT/HuggingFace repositories can contain internal .pkl files
            # that are NOT sklearn/joblib models (for example random state
            # snapshots). Never send those to joblib.load().
            lower = str(p).lower().replace("\\", "/")
            if "/bertphish/" in lower or "/transformers/" in lower:
                continue

            if p.name.lower().startswith("random_states_"):
                continue

            result.append(p)
    except OSError as exc:
        logger.warning("[PRETRAINED] Cannot scan %s: %s", root, exc)
    return sorted(set(result))

def find_transformer_dirs(root: Path) -> list[Path]:
    if not root.exists():
        return []

    roots = [root] if root.is_dir() else [root.parent]
    found = []

    for base in roots:
        try:
            candidates = [base] + [p for p in base.rglob("*") if p.is_dir()]
        except OSError:
            candidates = [base]

        for d in candidates:
            config = d / "config.json"
            weights = (
                (d / "model.safetensors").exists()
                or (d / "pytorch_model.bin").exists()
                or any(d.glob("*.safetensors"))
            )
            if config.exists() and weights:
                found.append(d.resolve())

    return list(dict.fromkeys(found))

def infer_task(path_or_name: str) -> Optional[str]:
    n = str(path_or_name).lower().replace("\\", "/")

    # Explicit names first.
    if any(x in n for x in [
        "review_classifier",
        "fake-review",
        "fake_review",
        "fake review",
        "fakereview",
    ]):
        return "review"

    if any(x in n for x in [
        "bertphish",
        "phishing",
        "phish",
    ]):
        return "phishing"

    if any(x in n for x in [
        "fake_news",
        "fake-news",
        "fake news",
        "fakenews",
        "truthlens",
    ]):
        return "news"

    # Generic "review" / "news" after explicit patterns.
    if "review" in n:
        return "review"
    if "news" in n:
        return "news"
    return None

def find_named(root: Path, names: list[str]) -> Optional[Path]:
    lowered = {x.lower() for x in names}
    for p in find_files(root):
        if p.name.lower() in lowered:
            return p
    return None

def register_pretrained(entry: dict[str, Any]):
    # Avoid duplicate registration by resolved model path/name.
    key = (entry.get("name"), str(entry.get("path", "")))
    for existing in pretrained_models:
        if (existing.get("name"), str(existing.get("path", ""))) == key:
            return
    pretrained_models.append(entry)
    logger.info(
        "[ENSEMBLE] Registered %-32s task=%s kind=%s",
        entry["name"],
        entry["task"],
        entry["kind"],
    )

def load_special_kaggle_pairs(root: Path):
    """
    Handles the exact multi-file structures discussed for the Kaggle
    models instead of trying to joblib.load() a directory.

    Fake news:
      fake_news_model.pkl
      tfidf_vectorizer.pkl

    Fake review:
      Review_classifier_LG.pkl
      scaling_pipeline.pkl
      vectorization_pipeline.pkl
    """
    # ---------------- Fake news pair ----------------
    fake_news_model_path = find_named(
        root,
        ["fake_news_model.pkl", "fake_news_model.joblib"],
    )
    fake_news_vec_path = find_named(
        root,
        [
            "tfidf_vectorizer.pkl",
            "tfidf_vectorizer.joblib",
            "vectorizer.pkl",
        ],
    )

    if fake_news_model_path and fake_news_vec_path:
        model = load_joblib(fake_news_model_path)
        vectorizer = load_joblib(fake_news_vec_path)
        if (
            model is not None
            and vectorizer is not None
            and hasattr(model, "predict")
            and hasattr(vectorizer, "transform")
        ):
            register_pretrained({
                "name": "Kaggle Fake News Model",
                "task": "news",
                "kind": "tfidf",
                "model": model,
                "vectorizer": vectorizer,
                "path": str(fake_news_model_path),
            })

    # ---------------- Fake review three-part pipeline ----------------
    review_model_path = find_named(
        root,
        ["Review_classifier_LG.pkl", "Review_classifier_LG.joblib"],
    )
    scaling_path = find_named(
        root,
        ["scaling_pipeline.pkl", "scaling_pipeline.joblib"],
    )
    vectorization_path = find_named(
        root,
        ["vectorization_pipeline.pkl", "vectorization_pipeline.joblib"],
    )

    if review_model_path and scaling_path and vectorization_path:
        model = load_joblib(review_model_path)
        scaler = load_joblib(scaling_path)
        vectorizer = load_joblib(vectorization_path)

        if (
            model is not None
            and scaler is not None
            and vectorizer is not None
            and hasattr(model, "predict")
            and hasattr(vectorizer, "transform")
            and hasattr(scaler, "transform")
        ):
            register_pretrained({
                "name": "Kaggle Fake Review Model",
                "task": "review",
                "kind": "review_pipeline",
                "model": model,
                "vectorizer": vectorizer,
                "scaler": scaler,
                "path": str(review_model_path),
            })

def load_generic_pretrained(root: Path):
    files = find_files(root)
    for file in files:
        # Special pairs are already registered.
        if file.name.lower() in {
            "fake_news_model.pkl",
            "fake_news_model.joblib",
            "tfidf_vectorizer.pkl",
            "tfidf_vectorizer.joblib",
            "review_classifier_lg.pkl",
            "review_classifier_lg.joblib",
            "scaling_pipeline.pkl",
            "scaling_pipeline.joblib",
            "vectorization_pipeline.pkl",
            "vectorization_pipeline.joblib",
        }:
            continue

        obj = load_joblib(file)
        if obj is None or not hasattr(obj, "predict"):
            continue

        task = infer_task(str(file))
        if not task:
            continue

        if task in {"news", "review"}:
            if hasattr(obj, "steps") or hasattr(obj, "named_steps"):
                register_pretrained({
                    "name": f"Pretrained {task.title()} Pipeline",
                    "task": task,
                    "kind": "pipeline",
                    "model": obj,
                    "path": str(file),
                })
                continue

            # Look for a companion vectorizer.
            candidates = [
                file.with_name(file.stem + "_vectorizer.joblib"),
                file.with_name(file.stem + "_vectorizer.pkl"),
                file.with_name("vectorizer.joblib"),
                file.with_name("vectorizer.pkl"),
                file.with_name("tfidf_vectorizer.joblib"),
                file.with_name("tfidf_vectorizer.pkl"),
            ]
            vectorizer = None
            for vp in candidates:
                if vp.exists():
                    candidate = load_joblib(vp)
                    if candidate is not None and hasattr(candidate, "transform"):
                        vectorizer = candidate
                        break

            if vectorizer is not None:
                register_pretrained({
                    "name": f"Pretrained {task.title()} Model",
                    "task": task,
                    "kind": "tfidf",
                    "model": obj,
                    "vectorizer": vectorizer,
                    "path": str(file),
                })

        elif task == "phishing":
            feature_count = getattr(obj, "n_features_in_", None)
            if feature_count in {5, 13, 21}:
                register_pretrained({
                    "name": f"Pretrained Phishing Model ({file.stem})",
                    "task": "phishing",
                    "kind": "url_features",
                    "model": obj,
                    "feature_count": int(feature_count),
                    "path": str(file),
                })
            else:
                logger.warning(
                    "[PRETRAINED] Skipping %s: unsupported phishing feature count=%s",
                    file,
                    feature_count,
                )

def load_pretrained_models():
    pretrained_models.clear()
    roots = read_model_paths()
    logger.info("[PRETRAINED] Scanning %d roots", len(roots))

    for root in roots:
        load_special_kaggle_pairs(root)

    for root in roots:
        load_generic_pretrained(root)

    logger.info(
        "[PRETRAINED] Registered sklearn/pipeline models: %d",
        len(pretrained_models),
    )

def load_bertphish():
    global bertphish_model, bertphish_tokenizer

    if os.getenv("ENABLE_BERTPHISH", "false").lower() != "true":
        logger.info("[BERTPhish] Disabled by ENABLE_BERTPHISH=false")
        return

    try:
        import transformers
        from transformers import AutoModelForSequenceClassification, AutoTokenizer
        logger.info("[BERTPhish] transformers=%s", getattr(transformers, "__version__", "unknown"))
    except Exception as exc:
        logger.warning(
            "[BERTPhish] transformers unavailable/incompatible: %s. "
            "Set ENABLE_BERTPHISH=false to run without BERTPhish.",
            exc,
        )
        return

    roots = read_model_paths() + [PRETRAINED_DIR]
    dirs = []
    for root in roots:
        dirs.extend(find_transformer_dirs(root))

    for directory in list(dict.fromkeys(dirs)):
        if "bertphish" not in str(directory).lower():
            continue

        try:
            logger.info("[BERTPhish] Loading %s", directory)
            tokenizer = AutoTokenizer.from_pretrained(
                str(directory),
                local_files_only=True,
            )
            model = AutoModelForSequenceClassification.from_pretrained(
                str(directory),
                local_files_only=True,
            )
            model.eval()
            bertphish_tokenizer = tokenizer
            bertphish_model = model
            logger.info("[BERTPhish] Loaded successfully.")
            return
        except Exception as exc:
            # This is intentionally non-fatal. A broken torchvision/
            # torch installation must not disable the other models.
            logger.warning(
                "[BERTPhish] Optional model failed: %s: %s",
                type(exc).__name__,
                exc,
            )

    logger.info("[BERTPhish] No compatible local model found.")
def load_hf_news_classifiers():
    global hf_news_classifiers
    hf_news_classifiers = []

    if not ENABLE_HF_NEWS_MODELS:
        logger.info("[HF-NEWS] Disabled by ENABLE_HF_NEWS_MODELS=false")
        return

    if not HF_NEWS_MODEL_IDS:
        return

    try:
        import transformers
        from transformers import AutoModelForSequenceClassification, AutoTokenizer
        logger.info("[HF-NEWS] transformers=%s", getattr(transformers, "__version__", "unknown"))
    except Exception as exc:
        logger.warning(
            "[HF-NEWS] transformers unavailable/incompatible: %s. "
            "Set ENABLE_HF_NEWS_MODELS=false to run without these voters.",
            exc,
        )
        return

    for repo_id in HF_NEWS_MODEL_IDS:
        try:
            logger.info("[HF-NEWS] Loading %s", repo_id)
            tokenizer = AutoTokenizer.from_pretrained(repo_id)
            model = AutoModelForSequenceClassification.from_pretrained(repo_id)
            model.eval()

            hf_news_classifiers.append({
                "name": f"HF: {repo_id.split('/')[-1]}",

                "repo_id": repo_id,
                "tokenizer": tokenizer,
                "model": model,
            })

            logger.info(
                "[HF-NEWS] Loaded %s | labels=%s",
                repo_id,
                getattr(model.config, "id2label", {}),
            )
        except Exception as exc:
            # A missing, renamed, private, or incompatible repo must never
            # take down the rest of the ensemble — it just doesn't vote.
            logger.warning(
                "[HF-NEWS] Skipping %s: %s: %s",
                repo_id, type(exc).__name__, exc,
            )

    logger.info("[HF-NEWS] %d/%d model(s) loaded", len(hf_news_classifiers), len(HF_NEWS_MODEL_IDS))
def load_all_models():
    MODEL_ERRORS.clear()
    MODEL_LOAD_EVENTS.clear()

    logger.info("==========================================")
    logger.info("TRUSTGUARD MODEL PATH DIAGNOSTICS")
    logger.info("BASE_DIR       = %s", BASE_DIR)
    logger.info("MODELS_DIR     = %s", MODELS_DIR)
    logger.info("MODELS_EXISTS  = %s", MODELS_DIR.exists())
    logger.info("PRETRAINED_DIR = %s", PRETRAINED_DIR)
    logger.info("PRETRAINED_EXISTS = %s", PRETRAINED_DIR.exists())
    if MODELS_DIR.exists():
        logger.info(
            "MODEL FILES = %s",
            [p.name for p in MODELS_DIR.iterdir() if p.is_file()],
        )
    logger.info("==========================================")
    logger.info(
        "[CONFIG] GEMINI_API_KEY=%s | GEMINI_MODEL=%s | BERTPHISH=%s | DOMAIN_AGE_LOOKUP=%s",
        "configured" if GEMINI_API_KEY else "not configured",
        GEMINI_MODEL,
        os.getenv("ENABLE_BERTPHISH", "false"),
        ENABLE_DOMAIN_AGE_LOOKUP,
    )
    if getattr(phishing_model, "n_features_in_", None) == 21:
        logger.warning(
            "[CONFIG] A 21-feature phishing model was detected. "
            "It will participate only when exact feature order is known."
        )

    load_local_models()
    load_pretrained_models()
    load_bertphish()
    load_hf_news_classifiers()

    # BUGFIX: previously never called, so news_registry stayed empty
    # forever. Must run last, after every model source above has loaded.
    build_news_registry()

    logger.info(
        "Models ready | news=%s review=%s phishing=%s pretrained=%d bertphish=%s hf_news=%d",
        bool(news_model is not None and news_vectorizer is not None),
        bool(review_model is not None and review_vectorizer is not None),
        phishing_model is not None,
        len(pretrained_models),
        bertphish_model is not None,
        len(hf_news_classifiers),
    )


def news_label(value: Any) -> str:
    v = str(value).strip().lower()
    if v in {"fake", "false", "0", "fake news", "f"}:
        return "Fake"
    if v in {"real", "true", "1", "real news", "r"}:
        return "Real"
    return "Unknown"

def review_label(value: Any) -> str:
    v = str(value).strip().lower()
    if v in {"fake", "false", "1", "spam", "fraud"}:
        return "Fake"
    if v in {"genuine", "real", "true", "0", "authentic"}:
        return "Genuine"
    return "Unknown"

def phishing_label(value: Any) -> str:
    v = str(value).strip().lower()
    if v in {
        "phishing", "phish", "malicious", "unsafe",
        "1", "attack", "true", "yes",
    }:
        return "Phishing"
    if v in {
        "safe", "legitimate", "benign", "normal",
        "0", "false", "no",
    }:
        return "Safe"
    return "Unknown"

def predict_model(model: Any, X: Any):
    try:
        raw = model.predict(X)[0]
    except Exception as exc:
        logger.warning(
            "Prediction failed for %s: %s",
            type(model).__name__,
            exc,
        )
        return None, None

    confidence = None
    if hasattr(model, "predict_proba"):
        try:
            probs = np.asarray(model.predict_proba(X)[0], dtype=float)
            classes = list(model.classes_)
            idx = classes.index(raw) if raw in classes else int(np.argmax(probs))
            confidence = float(probs[idx])
        except Exception as exc:
            logger.debug("predict_proba unavailable: %s", exc)

    return raw, confidence

def make_prediction(
    name: str,
    label: str,
    confidence: Optional[float],
    source: str = "ml",
    weight: float = 1.0,
):
    return {
        "model": name,
        "label": label,
        "confidence": (
            round(clamp01(confidence) * 100, 2)
            if confidence is not None
            else None
        ),
        "weight": float(weight),
        "source": source,
        "status": "participated",
    }

def safe_predict_text_model(
    model: Any,
    vectorizer: Any,
    content: str,
    task: str,
    name: str,
):
    try:
        X = vectorizer.transform([content])
        raw, conf = predict_model(model, X)
        if raw is None:
            return None
        label = news_label(raw) if task == "news" else review_label(raw)
        if label == "Unknown":
            return None
        return make_prediction(name, label, conf)
    except Exception as exc:
        logger.warning("[%s] %s failed: %s", task.upper(), name, exc)
        return None

def local_news_prediction(content: str):
    if news_model is None or news_vectorizer is None:
        return None
    return safe_predict_text_model(
        news_model,
        news_vectorizer,
        content,
        "news",
        "Local News Model",
    )

def local_review_prediction(content: str):
    if review_model is None or review_vectorizer is None:
        return None
    return safe_predict_text_model(
        review_model,
        review_vectorizer,
        content,
        "review",
        "Local Review Model",
    )

def pretrained_text_predictions(task: str, content: str):
    results = []

    for item in pretrained_models:
        if item["task"] != task:
            continue

        try:
            if item["kind"] == "pipeline":
                X = [content]
                raw, conf = predict_model(item["model"], X)

            elif item["kind"] == "tfidf":
                X = item["vectorizer"].transform([content])
                raw, conf = predict_model(item["model"], X)

            elif item["kind"] == "review_pipeline":
                vectorized = item["vectorizer"].transform([content])
                scaled = item["scaler"].transform(vectorized)
                raw, conf = predict_model(item["model"], scaled)

            else:
                continue

            if raw is None:
                continue

            label = news_label(raw) if task == "news" else review_label(raw)
            if label == "Unknown":
                continue

            results.append(
                make_prediction(
                    item["name"],
                    label,
                    conf,
                    source="pretrained",
                )
            )
        except Exception as exc:
            logger.warning(
                "[%s] %s failed: %s",
                task.upper(),
                item["name"],
                exc,
            )

    return results


SUSPICIOUS_KEYWORDS = (
    "login", "signin", "sign-in", "verify", "verification",
    "update-account", "secure-bank", "paypal", "netflix",
    "wallet", "crypto", "password", "credential", "confirm",
    "authentication", "reset-password", "account-verify",
)

SHADY_TLDS = (
    ".xyz", ".info", ".top", ".click", ".date", ".win",
    ".party", ".cc", ".loan", ".online", ".site",
)

def url_feature_data(url: str) -> dict[str, Any]:
    normalized = normalize_url(url)
    parsed = urlparse(normalized)
    host = (parsed.hostname or "").lower().rstrip(".")
    value = normalized.lower()

    ssl = int(parsed.scheme == "https")
    path = parsed.path or ""
    query = parsed.query or ""

    is_ip = 0
    try:
        ipaddress.ip_address(host)
        is_ip = 1
    except ValueError:
        pass

    keyword = int(any(k in value for k in SUSPICIOUS_KEYWORDS))
    shady_tld = int(any(host.endswith(tld) for tld in SHADY_TLDS))

    special_chars = sum(c in "-.?=&@_%#" for c in normalized)
    digit_count = sum(c.isdigit() for c in normalized)
    subdomains = max(0, len(host.split(".")) - 2)

    features13 = [
        ssl,
        keyword,
        special_chars,
        shady_tld,
        len(normalized),
        len(host),
        host.count("."),
        normalized.count("-"),
        digit_count,
        subdomains,
        is_ip,
        int("@" in normalized),
        int(bool(query)),
    ]

    features5 = [
        ssl,
        keyword,
        special_chars,
        shady_tld,
        len(normalized),
    ]

    # A 21-feature representation. For a third-party model this is used
    # only when the model exposes feature names or the environment provides
    # PHISHING_21_FEATURES. This prevents silently feeding arbitrary values
    # into a model whose training feature order is unknown.
    feature_map = {
        "url_length": len(normalized),
        "hostname_length": len(host),
        "path_length": len(path),
        "query_length": len(query),
        "dot_count": normalized.count("."),
        "slash_count": normalized.count("/"),
        "hyphen_count": normalized.count("-"),
        "underscore_count": normalized.count("_"),
        "question_count": normalized.count("?"),
        "equal_count": normalized.count("="),
        "at_count": normalized.count("@"),
        "ampersand_count": normalized.count("&"),
        "https": ssl,
        "ip_address": is_ip,
        "hyphen_in_hostname": int("-" in host),
        "suspicious_keyword": keyword,
        "shady_tld": shady_tld,
        "digit_count": digit_count,
        "special_char_count": special_chars,
        "subdomain_count": subdomains,
        "hostname_has_www": int(host.startswith("www.")),
    }

    return {
        "features5": features5,
        "features13": features13,
        "feature_map": feature_map,
        "ssl": ssl,
        "special_chars": special_chars,
        "shady_tld": shady_tld,
        "hostname": host,
    }

DEFAULT_21_FEATURE_ORDER = [
    "url_length",
    "hostname_length",
    "path_length",
    "query_length",
    "dot_count",
    "slash_count",
    "hyphen_count",
    "underscore_count",
    "question_count",
    "equal_count",
    "at_count",
    "ampersand_count",
    "https",
    "ip_address",
    "hyphen_in_hostname",
    "suspicious_keyword",
    "shady_tld",
    "digit_count",
    "special_char_count",
    "subdomain_count",
    "hostname_has_www",
]

def phishing_features_for_model(model: Any, url: str) -> Optional[list[float]]:
    data = url_feature_data(url)
    expected = getattr(model, "n_features_in_", None)

    if expected == 5:
        return data["features5"]

    if expected == 13:
        return data["features13"]

    if expected == 21:
        names = getattr(model, "feature_names_in_", None)
        if names is not None:
            order = [str(x).strip().lower() for x in names]
        else:
            env_order = os.getenv("PHISHING_21_FEATURES", "").strip()
            if not env_order:
                logger.warning(
                    "21-feature phishing model has no feature_names_in_. "
                    "Set PHISHING_21_FEATURES to the EXACT training feature order."
                )
                return None
            order = [x.strip().lower() for x in env_order.split(",") if x.strip()]

        missing = [x for x in order if x not in data["feature_map"]]
        if missing or len(order) != 21:
            logger.warning(
                "21-feature phishing model cannot be safely used: "
                "missing=%s order_length=%s",
                missing,
                len(order),
            )
            return None

        return [float(data["feature_map"][x]) for x in order]

    logger.warning(
        "Skipping phishing model: expected feature count=%s",
        expected,
    )
    return None

def phishing_prediction_for_model(
    model: Any,
    name: str,
    url: str,
    source: str = "ml",
):
    values = phishing_features_for_model(model, url)
    if values is None:
        return None

    try:
        X = np.asarray([values], dtype=float)
        raw, conf = predict_model(model, X)
        if raw is None:
            return None

        label = phishing_label(raw)
        if label == "Unknown":
            return None

        return make_prediction(
            name,
            label,
            conf,
            source=source,
        )
    except Exception as exc:
        logger.warning("[PHISHING] %s failed: %s", name, exc)
        return None

def local_phishing_prediction(url: str):
    if phishing_model is None:
        return None
    return phishing_prediction_for_model(
        phishing_model,
        "Local Phishing Model",
        url,
    )

def pretrained_phishing_predictions(url: str):
    results = []
    for item in pretrained_models:
        if item["task"] != "phishing":
            continue
        result = phishing_prediction_for_model(
            item["model"],
            item["name"],
            url,
            source="pretrained",
        )
        if result:
            results.append(result)
    return results


def bertphish_prediction(url: str):
    if bertphish_model is None or bertphish_tokenizer is None:
        return None

    try:
        import torch

        inputs = bertphish_tokenizer(
            url,
            return_tensors="pt",
            truncation=True,
            max_length=256,
            padding=True,
        )

        with torch.no_grad():
            output = bertphish_model(**inputs)

        probs = torch.softmax(output.logits, dim=-1)[0]
        index = int(torch.argmax(probs).item())

        id2label = getattr(bertphish_model.config, "id2label", {}) or {}
        label_name = str(id2label.get(index, "")).lower()

        if any(x in label_name for x in (
            "phish", "malicious", "unsafe", "attack", "fraud",
        )):
            label = "Phishing"
        elif any(x in label_name for x in (
            "safe", "benign", "legitimate", "normal", "clean",
        )):
            label = "Safe"
        else:
            # Some models use LABEL_0/LABEL_1. Respect an explicit
            # environment mapping instead of guessing silently.
            mapping = os.getenv("BERTPHISH_LABELS", "0=Safe,1=Phishing")
            pairs = {}
            for pair in mapping.split(","):
                if "=" in pair:
                    k, v = pair.split("=", 1)
                    pairs[k.strip()] = v.strip()
            label = pairs.get(str(index), "")
            if label not in {"Safe", "Phishing"}:
                logger.warning(
                    "[BERTPhish] Unknown label mapping: index=%s label=%s",
                    index,
                    label_name,
                )
                return None

        return make_prediction(
            "BERTPhish",
            label,
            float(probs[index].item()),
            source="transformer",
        )
    except Exception as exc:
        logger.warning("[BERTPhish] Prediction failed: %s", exc)
        return None
def hf_news_label(id2label: dict, index: int) -> str:
    raw = str(id2label.get(index, id2label.get(str(index), ""))).strip().lower()

    if any(x in raw for x in ("fake", "false", "unreliable", "misinformation")):
        return "Fake"
    if any(x in raw for x in ("real", "true", "reliable", "genuine")):
        return "Real"

    # LABEL_0 / LABEL_1-style output has no semantic name. Rather than
    # guess, fall back to an explicit mapping — same pattern as
    # BERTPHISH_LABELS. Override per your models' actual training order.
    mapping_env = os.getenv("HF_NEWS_LABEL_MAP", "0=Fake,1=Real")
    pairs = {}
    for pair in mapping_env.split(","):
        if "=" in pair:
            k, v = pair.split("=", 1)
            pairs[k.strip()] = v.strip()
    mapped = pairs.get(str(index), "")
    return mapped if mapped in {"Fake", "Real"} else "Unknown"


def hf_news_prediction(entry: dict[str, Any], content: str):
    try:
        import torch

        tokenizer = entry["tokenizer"]
        model = entry["model"]

        inputs = tokenizer(
            content,
            return_tensors="pt",
            truncation=True,

            max_length=512,
            padding=True,
        )

        with torch.no_grad():
            output = model(**inputs)

        probs = torch.softmax(output.logits, dim=-1)[0]
        index = int(torch.argmax(probs).item())

        id2label = getattr(model.config, "id2label", {}) or {}
        label = hf_news_label(id2label, index)

        if label == "Unknown":
            logger.warning(
                "[HF-NEWS] %s: could not resolve label for index=%s (id2label=%s)",
                entry["repo_id"], index, id2label,
            )
            return None

        return make_prediction(
            entry["name"],
            label,
            float(probs[index].item()),
            source="huggingface",
        )
    except Exception as exc:
        logger.warning("[HF-NEWS] %s prediction failed: %s", entry["repo_id"], exc)
        return None


def hf_news_predictions(content: str):

    results = []
    for entry in hf_news_classifiers:
        result = hf_news_prediction(entry, content)
        if result:
            results.append(result)
    return results

def registry_result_to_poll_dict(result: Any) -> Optional[dict[str, Any]]:
    """Convert a registry result into the prediction shape used by model_poll()."""
    if result is None:
        return None

    status = getattr(result, "status", None)
    label = getattr(result, "label", None)
    model = getattr(result, "model", None)
    confidence = getattr(result, "confidence", None)

    if status != "success" or not model or label in {None, "", "Unknown"}:
        return None

    return make_prediction(
        str(model),
        str(label),
        confidence,
        source="registry",
    )

def model_poll(predictions: list[dict[str, Any]], task: str) -> dict[str, Any]:
    """Aggregate compatible predictions into an inspectable ensemble result.

    A prediction contributes ``confidence * weight`` to its label.  This means
    model confidence and explicit voter weights affect both the winner and the
    reported confidence instead of being used only as a tie-breaker.
    """
    valid: list[dict[str, Any]] = []

    for prediction in predictions or []:
        if not prediction:
            continue
        if prediction.get("status") != "participated":
            continue
        label = prediction.get("label")
        if label in {None, "", "Unknown"}:
            continue

        try:
            confidence = clamp01(prediction.get("confidence"), 0.5)
            weight = max(0.1, float(prediction.get("weight", 1.0)))
        except (TypeError, ValueError):
            logger.warning("[POLL] Ignoring malformed prediction: %r", prediction)
            continue

        normalized = dict(prediction)
        normalized["confidence"] = round(confidence * 100, 2)
        normalized["weight"] = weight
        valid.append(normalized)

    if not valid:
        return {
            "winner": "Unknown",
            "votes": {},
            "weightedVotes": {},
            "weightedSharePercent": {},
            "totalVotes": 0,
            "winningVotes": 0,
            "confidence": 0,
            "voteRatioConfidence": 0,
            "weightedConfidence": 0,
            "margin": 0,
            "runnerUp": None,
            "isUnanimous": False,
            "isTie": False,
            "models": [],
            "task": task,
        }

    votes = Counter(p["label"] for p in valid)
    weighted: dict[str, float] = {}

    for prediction in valid:
        label = prediction["label"]
        confidence = clamp01(prediction.get("confidence"), 0.5)
        weight = max(0.1, float(prediction.get("weight", 1.0)))
        weighted[label] = weighted.get(label, 0.0) + confidence * weight

    # Weighted score is the primary decision signal.
    ranked = sorted(
        weighted.items(),
        key=lambda item: (item[1], votes.get(item[0], 0)),
        reverse=True,
    )
    winner = ranked[0][0]

    winning_votes = votes[winner]
    vote_ratio_confidence = winning_votes / len(valid)
    total_weighted = sum(weighted.values())

    weighted_confidence = (
        weighted[winner] / total_weighted if total_weighted > 0 else 0.0
    )

    runner_up = None
    margin = winning_votes
    if len(ranked) > 1:
        runner_label, runner_score = ranked[1]
        runner_votes = votes[runner_label]
        runner_up = {
            "label": runner_label,
            "votes": runner_votes,
            "weightedScore": round(runner_score, 4),
            "weightedSharePercent": round(
                (runner_score / total_weighted) * 100 if total_weighted else 0.0,
                2,
            ),
        }
        margin = winning_votes - runner_votes

    weighted_share_percent = {
        label: round((score / total_weighted) * 100 if total_weighted else 0.0, 2)
        for label, score in weighted.items()
    }

    return {
        "winner": winner,
        "votes": dict(votes),
        "weightedVotes": {label: round(score, 4) for label, score in weighted.items()},
        "weightedSharePercent": weighted_share_percent,
        "totalVotes": len(valid),
        "winningVotes": winning_votes,
        "confidence": round(weighted_confidence * 100, 2),
        "voteRatioConfidence": round(vote_ratio_confidence * 100, 2),
        "weightedConfidence": round(weighted_confidence * 100, 2),
        "margin": margin,
        "runnerUp": runner_up,
        "isUnanimous": len(votes) == 1,
        "isTie": len(ranked) > 1 and weighted[ranked[0][0]] == weighted[ranked[1][0]],
        "models": valid,
        "task": task,
    }


def extract_article(url: str) -> dict[str, Any]:
    url = normalize_url(url)

    fetch_result = safe_fetch_html(url, validate_public_url)
    if not fetch_result.ok:
        logger.warning("Article extraction failed for %s: %s", url, fetch_result.error)
        return {
            "title": "", "text": "", "published_at": None,
            "error": fetch_result.error,
            "errorMessage": fetch_result.error_message,
        }

    html = fetch_result.html

    try:
        import trafilatura
        extracted = trafilatura.extract(html, include_comments=False, include_tables=False)
        metadata = trafilatura.extract_metadata(html)

        if extracted:
            return {
                "title": clean_text(metadata.title if metadata else ""),
                "text": clean_text(extracted)[:MAX_ARTICLE_CHARS],
                "published_at": metadata.date if metadata else None,
                "error": None, "errorMessage": None,
            }
    except Exception as exc:
        logger.debug("Trafilatura parse failed on fetched HTML: %s", exc)

    # bs4 fallback reuses the SAME already-fetched HTML — no second
    # network round-trip, no chance of hitting the zstd bug twice.
    try:
        

        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "noscript", "svg"]):
            tag.decompose()

        title = soup.title.get_text(" ", strip=True) if soup.title else ""
        paragraphs = [p.get_text(" ", strip=True) for p in soup.find_all("p")]
        paragraphs = [p for p in paragraphs if len(p) >= 30]
        text = clean_text("\n".join(paragraphs))[:MAX_ARTICLE_CHARS]

        if not text:
            return {
                "title": clean_text(title), "text": "", "published_at": None,
                "error": "empty_content",
                "errorMessage": "The page loaded but no readable article text was found.",
            }

        return {
            "title": clean_text(title), "text": text, "published_at": None,
            "error": None, "errorMessage": None,
        }
    except Exception as exc:
        logger.warning("BeautifulSoup fallback failed: %s", exc)
        return {
            "title": "", "text": "", "published_at": None,
            "error": "parse_error", "errorMessage": "The page could not be parsed.",
        }

def get_gemini_client(request_key: Optional[str] = None):
    """Returns (client, key_used). key_used is None when request_key was
    supplied (per-user keys aren't tracked by the rotator/cooldown --
    that's the user's own quota to manage)."""
    api_key = (request_key or "").strip()
    if api_key:
        try:
            from google import genai
            return genai.Client(api_key=api_key), None
        except Exception as exc:
            logger.warning("Gemini request client failed: %s", exc)
            return None, None

    key = gemini_rotator.get_key()
    if not key:
        return None, None

    try:
        from google import genai
        return genai.Client(api_key=key), key
    except Exception as exc:
        logger.warning("Gemini initialization failed: %s", exc)
        return None, None

def extract_grounding_sources(response: Any) -> list[dict[str, str]]:
    sources = []
    seen = set()

    try:
        for candidate in getattr(response, "candidates", []) or []:
            metadata = getattr(candidate, "grounding_metadata", None)
            if metadata:
                chunks = getattr(metadata, "grounding_chunks", []) or []
                for chunk in chunks:
                    web = getattr(chunk, "web", None)
                    if not web:
                        continue
                    uri = str(getattr(web, "uri", "") or "").strip()
                    title = str(getattr(web, "title", "") or "").strip()
                    if uri and uri not in seen:
                        seen.add(uri)
                        sources.append({
                            "title": title or uri,
                            "url": uri,
                        })

            # Some SDK versions expose URL-context metadata separately.
            url_meta = getattr(candidate, "url_context_metadata", None)
            if url_meta:
                for meta in getattr(url_meta, "url_metadata", []) or []:
                    uri = str(getattr(meta, "retrieved_url", "") or "").strip()
                    if uri and uri not in seen:
                        seen.add(uri)
                        sources.append({
                            "title": uri,
                            "url": uri,
                        })
    except Exception as exc:
        logger.debug("Grounding source extraction failed: %s", exc)

    return sources[:15]
def gemini_news_check(
    headline: str,
    article_url: str,
    article_text: str,
    request_key: Optional[str] = None,
):
    """
    Verify a news article using Gemini when available.

    Behavior:
    - User-supplied API keys are never cached.
    - Server/shared Gemini results are cached.
    - Gemini API keys rotate on quota exhaustion.
    - Transient/API failures are never cached.
    - Falls back to local Python verification when Gemini is unavailable.
    """

    # 1. Cache only requests using the server's shared API keys.
    #
    # A user-provided key has its own quota, so its result must not
    # be shared with other users.
    cache_key = None

    if not request_key:
        cache_key = make_gemini_cache_key(
            headline,
            article_url,
            article_text,
        )

        cached = gemini_news_cache.get(cache_key)

        if cached is not None:
            logger.info("[CACHE] Gemini news check cache hit.")
            return cached

    # 2. Build the verification prompt.
    prompt = f"""
You are TrustGuard's independent news verification engine.

Check the following news claim using current web information.
Use independent sources and prefer primary/official sources.
Compare dates and context. Do not invent facts.
A claim being difficult to verify is not automatically fake.
Return uncertainty when evidence is insufficient.

HEADLINE:
{headline}

ARTICLE URL:
{article_url}

ARTICLE TEXT:
{article_text[:MAX_ARTICLE_CHARS]}

Return exactly:

LABEL: REAL or FAKE or UNKNOWN
REASON: concise evidence-based explanation
CLAIM: main claim being checked
UNCERTAINTY: important limitations
"""

    # 3. Determine how many keys we can try.
    #
    # For a user-provided key, only that key is allowed.
    # For server keys, rotate through available keys.
    attempts = (
        max(1, len(GEMINI_API_KEYS))
        if not request_key
        else 1
    )

    # 4. Try Gemini.
    for _attempt in range(attempts):
        client, key_used = get_gemini_client(request_key)

        if not client:
            logger.info(
                "No usable Gemini client available."
            )
            break

        try:
            from google.genai import types

            tools = [
                types.Tool(
                    google_search=types.GoogleSearch()
                )
            ]

            # URL grounding is useful when an article URL exists.
            if article_url:
                tools.append(
                    types.Tool(
                        url_context=types.UrlContext()
                    )
                )

            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    tools=tools,
                    temperature=0.1,
                ),
            )

            output = str(
                getattr(response, "text", "") or ""
            ).strip()

            # 5. Extract the normalized verdict.
            match = re.search(
                r"LABEL\s*:\s*(REAL|FAKE|UNKNOWN)",
                output.upper(),
            )

            if match and match.group(1) == "REAL":
                label = "Real"
            elif match and match.group(1) == "FAKE":
                label = "Fake"
            else:
                label = "Unknown"
            result = {
                "available": True,
                "label": label,
                "explanation": output,
                "sources": extract_grounding_sources(response),
                "mode": "gemini",
            }
            # 6. Cache ONLY successful server/shared-key results.
            #
            # Never cache results generated using a user's own key.
            if cache_key:
                gemini_news_cache.set(
                    cache_key,
                    result,
                )

                logger.info(
                    "[CACHE] Gemini news check result cached."
                )

            return result

        except Exception as exc:

            # 7. Rotate server keys when quota is exhausted.
            if key_used and is_quota_error(exc):
                logger.warning(
                    "Gemini key exhausted, rotating: %s",
                    exc,
                )

                gemini_rotator.mark_exhausted(
                    key_used
                )

                continue

            # 8. Non-quota error.
            #
            # Don't cache it. Fall back to the local verifier.
            logger.warning(
                "Gemini news check failed, "
                "falling back to offline verification: %s",
                exc,
            )

            break

    # 9. Gemini unavailable.
    #
    # The local verifier should still produce a verdict rather
    # than returning "Gemini unavailable".
    logger.info(
        "Gemini unavailable for news verification -- "
        "using offline Python fallback."
    )

    try:
        result = offline_news_verification(
            headline,
            article_text,
            extract_article,
            local_news_prediction,
        )
        result = _improve_offline_verification_result(result)
        return result

    except Exception as exc:
        # 10. Last-resort safety net.
        #
        # The verifier itself should never crash the request.
        logger.exception(
            "Offline news verification also failed: %s",
            exc,
        )

        return {
            "available": False,
            "label": "Unknown",
            "explanation": (
                "News verification could not be completed."
            ),
            "sources": [],
        }

@app.get("/cache/stats")
def cache_stats():
    from services.cache_service import cache_stats_all
    return cache_stats_all()
    
def gemini_generate(prompt: str, request_key: Optional[str] = None):
    attempts = max(1, len(GEMINI_API_KEYS)) if not request_key else 1

    last_error: Optional[Exception] = None
    for _attempt in range(attempts):
        client, key_used = get_gemini_client(request_key)
        if not client:
            raise HTTPException(
                status_code=503,
                detail=(
                    "Gemini is not configured or all keys are on cooldown. "
                    "Add GEMINI_API_KEY(S) to .env or send X-Gemini-API-Key."
                ),
            )

        try:
            response = client.models.generate_content(model=GEMINI_MODEL, contents=prompt)
            output = str(getattr(response, "text", "") or "").strip()
            if not output:
                raise RuntimeError("Gemini returned an empty response.")
            return output
        except Exception as exc:
            last_error = exc
            if key_used and is_quota_error(exc):
                logger.warning("Gemini key exhausted, rotating: %s", exc)
                gemini_rotator.mark_exhausted(key_used)
                continue
            logger.warning("Gemini request failed: %s", exc)
            raise HTTPException(status_code=502, detail=f"Gemini request failed: {exc}")

    raise HTTPException(
        status_code=503,
        detail=f"All configured Gemini keys are currently rate-limited: {last_error}",
    )
URL_IN_TEXT_RE = re.compile(r'https?://[^\s<>"\')\]]+')

def extract_urls(text: str) -> list[str]:
    if not text:
        return []
    found = [u.rstrip('.,;:!?') for u in URL_IN_TEXT_RE.findall(text)]
    seen = []
    for u in found:
        if u not in seen:
            seen.append(u)
    return seen[:10]
def sse_event(event_type: str, data: dict) -> str:
    return f"event: {event_type}\ndata: {json.dumps(data, default=str)}\n\n"


COMMONLY_SPOOFED_BRANDS = (
    "google", "paypal", "microsoft", "amazon", "netflix", "apple",
    "facebook", "instagram", "whatsapp", "bankofamerica", "chase",
    "wellsfargo", "americanexpress", "outlook", "gmail", "linkedin",
)

_HOMOGLYPH_MAP = str.maketrans({
    "0": "o", "1": "l", "3": "e", "4": "a", "5": "s", "7": "t", "8": "b", "$": "s",
})


def _improve_offline_verification_result(result: dict[str, Any]) -> dict[str, Any]:
    """
    offline_news_verification() runs when Gemini is unavailable. When it
    can't find any independent coverage it previously returned a blunt,
    technical explanation. This reframes that specific case with clearer,
    more actionable guidance, without touching cases where it DID find
    something to report.
    """
    result = dict(result)
    result.setdefault("mode", "offline")

    explanation = str(result.get("explanation") or "")
    no_coverage_markers = (
        "no independent web coverage",
        "no related articles",
        "could not be found",
    )

    if (
        result.get("label") == "Unknown"
        and not result.get("sources")
        and any(marker in explanation.lower() for marker in no_coverage_markers)
    ):
        result["explanation"] = (
            "We couldn't independently confirm this claim right now "
            "(Gemini web verification is unavailable, so we fell back to a "
            "free web search). That's inconclusive, not a red flag by "
            "itself — it commonly happens with breaking news, very local "
            "or niche stories, or a temporarily unreachable search "
            "backend. Treat the other model votes below as the primary "
            "signal, and consider checking the original source or a "
            "dedicated fact-checking site directly."

        )

    return result

def detect_lookalike_brand(hostname: str) -> Optional[str]:
    """
    Flags a domain as a likely lookalike ONLY when, after normalizing
    common digit/symbol-for-letter substitutions (0->o, 1->l, 3->e, ...),
    its core label becomes an exact or near-exact match for a well-known,
    frequently-spoofed brand name.

    BUGFIX: this replaces a blanket regex (`[a-z][0-9][a-z]` /
    `[0-9][a-z][0-9]`) that fired on ANY domain containing a
    letter-digit-letter run anywhere -- which matches extremely common,
    entirely legitimate domain patterns such as "b2b.com", "4u.com",
    "2go.com", or "office365.com", making the URL-trust signal noisy and
    frequently wrong. It now only fires when undoing the substitution
    reveals a real, commonly-impersonated brand name.
    """
    if not hostname:
        return None

    core = hostname.split(".")[0]
    normalized = core.translate(_HOMOGLYPH_MAP)

    if normalized == core:
        # No digit/symbol substitution present at all -- nothing to flag.
        return None

    for brand in COMMONLY_SPOOFED_BRANDS:
        if normalized == brand or similarity(normalized, brand) >= 0.88:
            return brand

    return None


def assess_url_trust(url: str, strict: bool = True) -> dict[str, Any]:
    """
    strict=True is used for the article's own URL and any URL explicitly
    cited in the headline. strict=False is used for URLs merely found
    embedded inside pasted body text, where weak/noisy signals (missing
    HTTPS, high special-char count from tracking params, deep subdomain
    nesting from CDNs) are extremely common on completely legitimate
    sites and should not by themselves brand a source untrustworthy.
    """
    data = url_feature_data(url)
    reputation = domain_reputation(data["hostname"])

    if reputation == "trusted":
        return {
            "url": url, "hostname": data["hostname"], "trusted": True,
            "reasons": ["recognized trusted news/government domain"],
            "reputation": "trusted",
        }

    reasons = []

    # Strong signals: meaningful regardless of whether this is the
    # article's own address or an incidental body-embedded link.
    if data["shady_tld"]:
        reasons.append("suspicious top-level domain")
    if reputation == "shady":
        reasons.append("domain pattern associated with low-quality content farms")
    try:
        ip = ipaddress.ip_address(data["hostname"])
        reasons.append("raw IP address instead of domain" if ip.is_global
                        else "private/non-public IP address")
    except ValueError:
        pass
    lookalike_of = detect_lookalike_brand(data["hostname"])
    if lookalike_of:
        reasons.append(f"possible lookalike domain of '{lookalike_of}'")

    # Weak signals: only checked in strict mode (see docstring above).
    if strict:
        if not data["ssl"]:
            reasons.append("no HTTPS")
        if data["special_chars"] > 10:
            reasons.append("excessive special characters")
        if data["hostname"] and data["hostname"].count(".") > 3:
            reasons.append("unusually deep subdomain nesting")

    return {
        "url": url, "hostname": data["hostname"],
        "trusted": len(reasons) == 0, "reasons": reasons,
        "reputation": reputation,
    }

def search_based_url_trust(headline: str, article_text: str = "") -> dict[str, Any]:
    """
    When no article URL/embedded links were supplied, search for who is
    covering the claim and assess the trustworthiness of those domains.
    Pure Python — search engine only, no AI model.
    """
    query = headline.strip() or article_text[:200].strip()
    if not query:
        return {"performed": False, "reason": "No headline or text to search."}

    urls = search_related_urls(query, max_results=8)
    if not urls:
        return {
            "performed": True, "checked": [], "trustedCount": 0,
            "untrustworthyCount": 0, "totalChecked": 0,
            "coverageFound": False,
            "reason": "No related coverage found via search.",
        }

    checked = [assess_url_trust(u) for u in urls]
    trusted = sum(1 for c in checked if c["trusted"])

    return {
        "performed": True, "checked": checked,
        "trustedCount": trusted,
        "untrustworthyCount": len(checked) - trusted,
        "totalChecked": len(checked),
        "coverageFound": True,
    }

def check_article_url_trust(headline: str, article_text: str, article_url: str) -> dict[str, Any]:
    """
    BUGFIX ("news URL trust check not working properly"): this used to
    pull every URL out of the ENTIRE pasted article body and judge each
    one with the same strict checklist as the article's own address.
    Real article text -- even from completely reputable outlets --
    routinely contains links to trackers, share widgets, related-reading
    boxes, and ad partners, so this produced frequent false
    "untrustworthy" hits with nothing to do with the claim itself. Now:
      - the article's own URL and any URL explicitly cited in the
        HEADLINE are checked strictly and drive the vote on their own;
      - URLs merely found embedded inside the body text are checked
        leniently and only contribute if there's an actual pattern of
        them (2+), not a single incidental tracker link.
    """
    primary_candidates = ([article_url] if article_url else []) + extract_urls(headline)
    body_candidates = extract_urls(article_text)

    seen: set[str] = set()
    primary_results = []
    for u in primary_candidates:
        norm = normalize_url(u)
        if norm in seen:
            continue
        seen.add(norm)
        primary_results.append(assess_url_trust(norm, strict=True))

    body_results = []
    for u in body_candidates:
        norm = normalize_url(u)
        if norm in seen:
            continue
        seen.add(norm)
        body_results.append(assess_url_trust(norm, strict=False))

    untrustworthy_primary = [r for r in primary_results if not r["trusted"]]
    untrustworthy_body = [r for r in body_results if not r["trusted"]]

    any_untrustworthy = bool(untrustworthy_primary) or len(untrustworthy_body) >= 2

    return {
        "checked": primary_results + body_results,
        "primary": primary_results,
        "bodyEmbedded": body_results,
        "untrustworthyCount": len(untrustworthy_primary) + len(untrustworthy_body),
        "anyUntrustworthy": any_untrustworthy,
    }

def extract_keywords(text: str, limit: int = 8) -> list[str]:
    words = re.findall(r"[a-zA-Z0-9]{3,}", text.lower())
    words = [w for w in words if w not in STOPWORDS]
    # Preserve order, dedupe, keep the most distinctive (longer) tokens first
    seen = []
    for w in sorted(set(words), key=lambda x: -len(x)):
        if w in words and w not in seen:
            seen.append(w)
    return seen[:limit]

def similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def _pib_empty_result(reason: str, near_miss: Optional[dict] = None) -> dict[str, Any]:
    return {
        "available": True,
        "covered": False,
        "label": "Unknown",
        "explanation": reason + (
            f" (closest: \"{near_miss['title']}\", score {near_miss.get('score', 0):.2f})"
            if near_miss else ""
        ),
        "sources": [],
    }

def stream_news_analysis(headline: str, article_url: str, article_text: str, request_key: Optional[str]):
    """
    §21/§24: live progress for a news analysis, as a generator of SSE
    frames. Calls the SAME functions analyze_news() uses — this is
    intentionally NOT a refactor of that endpoint (see rationale above
    the code block in the response this came with). Any bug here
    cannot affect POST /analyze/news, since that code path is untouched.
    """
    analysis_id = "TG-" + datetime.now(timezone.utc).strftime("%Y-%m-%d") + "-" + uuid.uuid4().hex[:8].upper()
    started = time.perf_counter()

    yield sse_event("analysis_started", {"analysisId": analysis_id})

    try:
        headline = clean_text(headline)
        article_url = clean_text(article_url)
        article_text = clean_text(article_text)

        extracted = {"title": "", "text": "", "published_at": None}
        if article_url:
            try:
                validate_public_url(article_url)
                article_url = normalize_url(article_url)
            except ValueError as exc:
                yield sse_event("error", {"stage": "url_validation", "message": str(exc)})
                yield sse_event("analysis_completed", {"analysisId": analysis_id, "status": "FAILED"})
                return

            yield sse_event("article_extraction_started", {"url": article_url})
            extracted = extract_article(article_url)
            if extracted.get("error"):
                yield sse_event("article_extraction_failed", {"url": article_url, "reason": extracted.get("errorMessage")})
            else:
                yield sse_event("article_extraction_completed", {"url": article_url, "titleFound": bool(extracted.get("title"))})

            if not headline:
                headline = extracted["title"]
            if not article_text:
                article_text = extracted["text"]

        content = "\n".join(x for x in [headline, article_text] if x)[:MAX_INPUT_CHARS]
        if len(content.strip()) < 15:
            yield sse_event("error", {"stage": "input_validation", "message": "Supplied content is too short for analysis."})
            yield sse_event("analysis_completed", {"analysisId": analysis_id, "status": "FAILED"})
            return

        # --- Claim extraction --------------------------------------------
        yield sse_event("claim_extraction_started", {})
        structured_claim = None
        suggested_queries: list[str] = []
        try:
            structured_claim = build_structured_claim(headline, article_text)
            suggested_queries = claim_to_search_queries(structured_claim)
            yield sse_event("claim_extracted", {"claim": structured_claim.to_dict()})
        except Exception as exc:
            logger.warning("[STREAM] claim extraction failed: %s", exc)
            yield sse_event("claim_extraction_failed", {"message": str(exc)})

        # --- Primary-content model poll (Level 1, §16) --------------------
        predictions = []

        yield sse_event("model_started", {"model": "Local News Model"})
        local = local_news_prediction(content)
        if local:
            predictions.append(local)
            yield sse_event("model_completed", {"model": "Local News Model", "label": local["label"], "confidence": local["confidence"]})
        else:
            yield sse_event("model_unavailable", {"model": "Local News Model"})

        for item in [p for p in pretrained_models if p["task"] == "news"]:
            yield sse_event("model_started", {"model": item["name"]})
            result = predict_pretrained_item(item, content)
            if result:
                predictions.append(result)
                yield sse_event("model_completed", {"model": item["name"], "label": result["label"], "confidence": result["confidence"]})
            else:
                yield sse_event("model_unavailable", {"model": item["name"]})

        for entry in hf_news_classifiers:
            yield sse_event("model_started", {"model": entry["name"]})
            result = hf_news_prediction(entry, content)
            if result:
                predictions.append(result)
                yield sse_event("model_completed", {"model": entry["name"], "label": result["label"], "confidence": result["confidence"]})
            else:
                yield sse_event("model_unavailable", {"model": entry["name"]})

        # Always-available zero-dependency stylometric voter, mirrored
        # from analyze_news() so the live stream never has fewer voters
        # than the non-streaming endpoint.
        yield sse_event("model_started", {"model": "Heuristic Style Check"})
        heuristic_vote = heuristic_news_vote(headline, article_text, make_prediction)
        if heuristic_vote:
            predictions.append(heuristic_vote)
            yield sse_event("model_completed", {"model": "Heuristic Style Check", "label": heuristic_vote["label"], "confidence": heuristic_vote["confidence"]})
        else:
            yield sse_event("model_unavailable", {"model": "Heuristic Style Check"})

        # URL Trust Analysis — same single-call logic as analyze_news().
        embedded_url_trust = check_article_url_trust(headline, article_text, article_url)
        if embedded_url_trust["anyUntrustworthy"]:
            url_trust_vote = make_prediction("URL Trust Analysis", "Fake", 0.7, source="heuristic", weight=1.3)
            predictions.append(url_trust_vote)
            yield sse_event("model_completed", {"model": "URL Trust Analysis", "label": "Fake", "confidence": url_trust_vote["confidence"]})
        else:
            yield sse_event("model_unavailable", {"model": "URL Trust Analysis"})

        poll = model_poll(predictions, "Fake News")
        yield sse_event("vote_added", {"votes": poll["votes"], "winner": poll["winner"], "totalVotes": poll["totalVotes"]})

        # --- PIB Fact Check (independent voter, live-poll enabled) ---------
        # Runs regardless of whether URLs were supplied, exactly like
        # analyze_news(). Wrapped defensively: a PIB outage must never
        # abort the whole live stream.
        yield sse_event("model_started", {"model": "PIB Fact Check"})
        try:
            pib = pib_fact_check(headline, article_text)
        except Exception as exc:
            logger.warning("[STREAM] PIB fact-check failed: %s", exc)
            pib = {"available": False, "covered": False, "label": "Unknown", "explanation": str(exc), "sources": []}

        if pib.get("covered") and pib["label"] in {"Real", "Fake"}:
            pib_vote = make_prediction("PIB Fact Check", pib["label"], None, source="pib", weight=1.5)
            predictions.append(pib_vote)
            yield sse_event("model_completed", {"model": "PIB Fact Check", "label": pib["label"], "confidence": pib_vote["confidence"]})
        else:
            yield sse_event("model_unavailable", {"model": "PIB Fact Check", "reason": pib.get("explanation")})

        poll = model_poll(predictions, "Fake News")
        yield sse_event("vote_added", {"votes": poll["votes"], "winner": poll["winner"], "totalVotes": poll["totalVotes"]})

        # --- Search Coverage Trust (independent voter, live-poll enabled) --
        # Only meaningful when the article/headline supplied no links of
        # its own to check directly — mirrors analyze_news() exactly.
        search_url_trust = None
        if not embedded_url_trust["checked"]:
            yield sse_event("model_started", {"model": "Search Coverage Trust"})
            try:
                search_url_trust = search_based_url_trust(headline, article_text)
            except Exception as exc:
                logger.warning("[STREAM] Search Coverage Trust failed: %s", exc)
                search_url_trust = {"performed": False, "reason": str(exc)}

        search_url_trust = None
        if not embedded_url_trust["checked"]:
            yield sse_event("model_started", {"model": "Search Coverage Trust"})
            try:
                search_url_trust = search_based_url_trust(headline, article_text)
            except Exception as exc:
                logger.warning("[STREAM] Search Coverage Trust failed: %s", exc)
                search_url_trust = {"performed": False, "reason": str(exc)}

            search_trust_vote = None
            if search_url_trust.get("coverageFound"):
                total = search_url_trust["totalChecked"]
                trust_ratio = search_url_trust["trustedCount"] / total if total else 0
                if total >= 3:
                    if trust_ratio >= 0.6:
                        search_trust_vote = make_prediction("Search Coverage Trust", "Real", trust_ratio, source="heuristic", weight=1.2)
                    elif trust_ratio <= 0.35:
                        search_trust_vote = make_prediction("Search Coverage Trust", "Fake", 1 - trust_ratio, source="heuristic", weight=1.2)
            

            if search_trust_vote:
                predictions.append(search_trust_vote)
                yield sse_event("model_completed", {"model": "Search Coverage Trust", "label": search_trust_vote["label"], "confidence": search_trust_vote["confidence"]})
            else:
                yield sse_event("model_unavailable", {"model": "Search Coverage Trust", "reason": search_url_trust.get("reason") if search_url_trust else "not applicable"})
            poll = model_poll(predictions, "Fake News")
            yield sse_event("vote_added", {"votes": poll["votes"], "winner": poll["winner"], "totalVotes": poll["totalVotes"]})

        # --- Gemini (independent voter) -------------------------------------
        yield sse_event("model_started", {"model": "Gemini + Google Search"})
        gemini = gemini_news_check(headline, article_url, article_text, request_key)
        if gemini["label"] in {"Real", "Fake"}:
            predictions.append(make_prediction("Gemini + Google Search", gemini["label"], None, source="gemini"))
            yield sse_event("model_completed", {"model": "Gemini + Google Search", "label": gemini["label"], "confidence": None})
        else:
            yield sse_event("model_unavailable", {"model": "Gemini + Google Search", "reason": gemini.get("explanation")})

        poll = model_poll(predictions, "Fake News")
        yield sse_event("vote_added", {"votes": poll["votes"], "winner": poll["winner"], "totalVotes": poll["totalVotes"]})

        # --- Temporal ------------------------------------------------------
        temporal_assessment = None
        try:
            mentioned_dates = structured_claim.entities.dates if structured_claim else []
            temporal_assessment = classify_currentness(extracted.get("published_at"), mentioned_dates)
            yield sse_event("temporal_classified", {"temporal": temporal_assessment.to_dict()})
        except Exception as exc:
            logger.warning("[STREAM] temporal classification failed: %s", exc)

        # --- Search + per-article ML + clustering (§10/§11/§13) -------------
        #
        # BUGFIX: article fetching used to be a plain sequential
        # `for result in search_results: extract_article(result.url)`
        # loop, even though ThreadPoolExecutor/as_completed were already
        # imported and SEARCH_FETCH_WORKERS was already configurable —
        # neither was ever actually used, so up to MAX_SEARCH_ARTICLES_TO_FETCH
        # network fetches ran one at a time. Fetching (the network-bound
        # part) is now parallelized across SEARCH_FETCH_WORKERS threads;
        # the ML inference on each fetched article still runs sequentially
        # afterwards (as each future completes) so model objects are never
        # called concurrently from multiple threads.
        related_evidence = {"enabled": False, "articles": [], "clusters": [], "summary": None}
        if ENABLE_WEB_SEARCH_VERIFICATION and suggested_queries:
            yield sse_event("search_started", {"queries": suggested_queries})
            try:
                search_results = _search_service.multi_query_search(suggested_queries, max_results_per_query=6)
                search_results = search_results[:MAX_SEARCH_ARTICLES_TO_FETCH]
                yield sse_event("search_completed", {"resultsFound": len(search_results)})
            except Exception as exc:
                search_results = []
                yield sse_event("search_failed", {"message": str(exc)})

            fetched = []
            worker_count = max(1, min(SEARCH_FETCH_WORKERS, len(search_results))) if search_results else 1

            with ThreadPoolExecutor(max_workers=worker_count) as executor:
                future_to_result = {}
                for result in search_results:
                    yield sse_event("article_found", {"url": result.url, "domain": result.domain})
                    future_to_result[executor.submit(extract_article, result.url)] = result

                for future in as_completed(future_to_result):
                    result = future_to_result[future]
                    try:
                        article_extracted = future.result()
                    except Exception as exc:
                        yield sse_event("article_extraction_failed", {"url": result.url, "reason": str(exc)})
                        continue

                    if article_extracted.get("error") or not article_extracted.get("text"):
                        yield sse_event("article_extraction_failed", {"url": result.url, "reason": article_extracted.get("errorMessage")})
                        continue

                    article_id = hashlib.sha256(result.url.encode()).hexdigest()[:12]
                    entry = {
                        "id": article_id, "url": result.url, "domain": result.domain,
                        "title": article_extracted.get("title") or result.title,
                        "text": article_extracted.get("text"),
                        "publishedAt": article_extracted.get("published_at"),
                    }
                    yield sse_event("article_extracted", {"url": result.url, "id": article_id})
                    yield sse_event("article_analysis_started", {"id": article_id, "url": result.url})

                    registry_results = news_registry.run("news", entry["text"])
                    for r in registry_results:
                        yield sse_event(
                            "model_completed" if r.status == "success" else "model_unavailable",
                            {"model": r.model, "articleId": article_id, "label": r.label, "confidence": r.confidence},
                        )
                    article_predictions = [p for p in (registry_result_to_poll_dict(r) for r in registry_results) if p]
                    article_poll = model_poll(article_predictions, "Article ML Poll")
                    entry["mlPoll"] = {
                        "winner": article_poll["winner"], "votes": article_poll["votes"],
                        "totalVotes": article_poll["totalVotes"], "confidence": article_poll["confidence"],
                    }
                    entry["articleLabelAgreement"] = (
                        "INSUFFICIENT" if article_poll["winner"] == "Unknown"
                        else "MATCHES_PRIMARY" if article_poll["winner"] == poll["winner"]
                        else "DIFFERS_FROM_PRIMARY"
                    )
                    yield sse_event("article_analyzed", {
                        "id": article_id, "url": result.url,
                        "winner": article_poll["winner"], "agreement": entry["articleLabelAgreement"],
                    })
                    fetched.append(entry)

            yield sse_event("source_clustering_started", {})
            cluster_inputs = [ArticleForClustering(id=a["id"], url=a["url"], domain=a["domain"], title=a["title"]) for a in fetched]
            clusters = cluster_articles(cluster_inputs)
            summary = independence_summary(clusters)
            yield sse_event("source_cluster_created", {"clusterCount": len(clusters), "totalArticles": summary["totalArticles"]})

            related_evidence = {
                "enabled": True, "articlesFound": len(search_results), "articlesExtracted": len(fetched),
                "articles": fetched, "clusters": [c.to_dict() for c in clusters], "summary": summary,
            }
        else:
            yield sse_event("search_skipped", {"reason": "ENABLE_WEB_SEARCH_VERIFICATION is false or no queries generated"})

        # --- Synthesis -------------------------------------------------------
        yield sse_event("cross_evidence_started", {})
        python_synthesis = None
        try:
            python_synthesis = synthesize(
                poll=poll,
                temporal=temporal_assessment.to_dict() if temporal_assessment else None,
                clickbait=structured_claim.clickbait if structured_claim else None,
                gemini_available=gemini["available"],
            )
            yield sse_event("cross_evidence_completed", {
                "classification": python_synthesis.classification, "confidence": python_synthesis.confidence,
            })
        except Exception as exc:
            logger.warning("[STREAM] synthesis failed: %s", exc)

        winner = poll["winner"]
        final_result = {
            "success": True,
            "label": winner,
            "confidence": poll["confidence"],
            "badgeClass": "success" if winner == "Real" else "danger" if winner == "Fake" else "warning",
            "metrics": {
                "modelVotes": poll["votes"], "totalModels": poll["totalVotes"],
                "participatingModels": [p["model"] for p in predictions],
            },
            "explanation": (
                f"{poll['winningVotes']} of {poll['totalVotes']} participating voters selected {winner}."
                if winner != "Unknown" else "No model produced a usable result."
            ),
            "poll": poll,
            "models": predictions,
            "claim": structured_claim.to_dict() if structured_claim else None,
            "temporal": temporal_assessment.to_dict() if temporal_assessment else None,
            "pythonSynthesis": python_synthesis.to_dict() if python_synthesis else None,
            "relatedEvidence": related_evidence,
            
            "pibFactCheck": {
                "available": pib.get("available", False),
                "covered": pib.get("covered", False),
                "vote": pib.get("label", "Unknown"),
                "explanation": pib.get("explanation", ""),
                "sources": pib.get("sources", []),
            },
            "urlTrust": {
                "embedded": embedded_url_trust,
                "searchBased": search_url_trust,
            },
            "webVerification": {
                "available": gemini["available"], "vote": gemini["label"],
                "mode": gemini.get("mode", "gemini"),
                "explanation": gemini["explanation"], "sources": gemini["sources"],
            },
            "relatedNews": gemini["sources"],
            "input": {"headline": headline, "articleUrl": article_url, "articleExtracted": bool(extracted.get("text"))},
        }

        yield sse_event("final_result", final_result)
        yield sse_event("analysis_completed", {
            "analysisId": analysis_id, "status": "COMPLETED",
            "durationMs": round((time.perf_counter() - started) * 1000, 1),
        })

    except Exception as exc:
        logger.exception("[STREAM] pipeline crashed")
        yield sse_event("error", {"stage": "pipeline", "message": str(exc)})
        yield sse_event("analysis_completed", {"analysisId": analysis_id, "status": "FAILED"})


@app.post("/analyze/news/stream")
def analyze_news_stream(payload: NewsPayload, x_gemini_api_key: Optional[str] = Header(default=None)):
    return StreamingResponse(
        stream_news_analysis(payload.headline or payload.text, payload.article_url, payload.article_text, x_gemini_api_key),
        media_type="text/event-stream; charset=utf-8",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )


def find_pib_posts(query: str, max_results: int = 6) -> list[dict[str, str]]:
    """
    Finds PIB Fact Check posts via two independent, AI-free routes:
    1. PIB's own site search
    2. A site-restricted general web search (site:pib.gov.in)
    Both are combined and deduplicated for redundancy.
    """
    found = []

    # Route 1: PIB's own search
    #
    # BUGFIX ("pib check not working properly"): this used to accept
    # ANY anchor tag on the search-results page with 15+ characters of
    # link text -- including nav bars, footers, and social-share links
    # unrelated to any actual fact-check post -- flooding the candidate
    # list with junk that then had to be scored/fetched for nothing.
    # Obvious non-article links (assets, feeds, tag/category pages,
    # anchors, scripts) are now filtered out up front.
    ignored_href_patterns = (
        "javascript:", "mailto:", "#", "/wp-json/", "/tag/", "/category/",
        "/feed", ".jpg", ".jpeg", ".png", ".gif", ".svg", ".pdf", ".css", ".js",
    )
    try:
        response = requests.get(
            PIB_FACTCHECK_SEARCH_URL,
            params={"q": query},
            timeout=PIB_SEARCH_TIMEOUT,
            headers={"User-Agent": "Mozilla/5.0 TrustGuard/1.0"},
        )
        if response.ok:
            soup = BeautifulSoup(response.text, "html.parser")
            for link in soup.find_all("a", href=True):
                href = link["href"]
                if any(pat in href.lower() for pat in ignored_href_patterns):
                    continue
                title = link.get_text(" ", strip=True)
                if len(title) >= 15:
                    if not href.startswith("http"):
                        href = PIB_FACTCHECK_BASE.rstrip("/") + "/" + href.lstrip("/")
                    found.append({"title": title, "url": href})
    except Exception as exc:
        logger.debug("PIB direct search failed: %s", exc)

    # Route 2: general search restricted to pib.gov.in (reuses existing scraper)
    try:
        site_query = f"site:pib.gov.in {query}"
        for url in search_related_urls(site_query, max_results=max_results):
            if "pib.gov.in" in url.lower():
                found.append({"title": "", "url": url})
    except Exception as exc:
        logger.debug("Site-restricted PIB search failed: %s", exc)

    # Fetch missing titles for route-2 results (needed for verdict parsing)
    for item in found:
        if not item["title"]:
            item["title"] = fetch_page_title(item["url"]) or item["url"]

    # Dedupe by URL
    seen, unique = set(), []
    for item in found:
        if item["url"] not in seen:
            seen.add(item["url"])
            unique.append(item)

    return unique[:max_results]


def fetch_page_title(url: str) -> str:
    try:
        r = requests.get(url, timeout=8, headers={"User-Agent": "Mozilla/5.0 TrustGuard/1.0"})
        if r.ok:
            soup = BeautifulSoup(r.text, "html.parser")
            if soup.title:
                return soup.title.get_text(" ", strip=True)
    except Exception:
        pass
    return ""

def keyword_overlap_score(query_keywords: list[str], title: str, query_text: str = "") -> float:
    """
    BUGFIX ("pib check not working properly"): this returned a hard 0.0
    whenever extract_keywords() found nothing to extract -- which
    happens for short or stopword-heavy headlines -- so those headlines
    could never match a real PIB post no matter how relevant, since 0.0
    never clears MATCH_THRESHOLD. When there are no usable keywords we
    now fall back to raw string similarity (via the existing
    similarity() helper) between the original query text and the
    candidate title, at a reduced weight, instead of an automatic zero.
    """
    title_words = set(re.findall(r"[a-zA-Z0-9]{3,}", title.lower()))
    query_set = set(query_keywords)
    if not query_set or not title_words:
        return similarity(query_text, title) * 0.5 if query_text and title else 0.0
    intersection = query_set & title_words
    union = query_set | title_words
    jaccard = len(intersection) / len(union) if union else 0.0
    coverage = len(intersection) / len(query_set)  # how much of the claim is represented
    return (jaccard * 0.4) + (coverage * 0.6)

FAKE_VERDICT_PATTERNS = (
    r"❌", r"\bfake\b", r"\bmisleading\b", r"\bmorphed\b", r"\bfabricated\b",
    r"\bfalse\b", r"\buntrue\b", r"\bbaseless\b", r"\bhoax\b", r"\brumou?r\b",
    r"\bdoctored\b", r"\bdistorted\b", r"\bno such\b", r"\bdoes not exist\b",
    r"\bnot true\b", r"\bnot correct\b",
)
REAL_VERDICT_PATTERNS = (
    r"✅", r"\bgenuine\b", r"\btrue claim\b", r"\bconfirmed\b",
    r"\bauthentic\b", r"\baccurate\b", r"\bcorrect claim\b",
)

def parse_pib_verdict(title: str, snippet: str = "") -> Optional[str]:
    """
    BUGFIX ("pib check not working properly"): the old version matched
    fixed-order substrings like "false claim", which misses the extremely
    common real-world phrasing "the claim is false" (same words, reverse
    order) -- so PIB pages that clearly stated a claim was false were
    routinely scored as having no identifiable verdict. Word-boundary
    regexes match the words regardless of order or surrounding sentence
    structure. The overly-broad "does not" marker (matched almost any
    negative sentence, verdict or not) has been dropped in favor of more
    specific phrasings.
    """
    text = f"{title} {snippet}".lower()

    fake_hits = sum(1 for pat in FAKE_VERDICT_PATTERNS if re.search(pat, text))
    real_hits = sum(1 for pat in REAL_VERDICT_PATTERNS if re.search(pat, text))

    # Require a clear majority, not just any single match, to avoid
    # misreading a post that merely *quotes* the claim being debunked.
    if fake_hits > real_hits and fake_hits >= 1:
        return "Fake"
    if real_hits > fake_hits and real_hits >= 1:
        return "Real"
    return None
def search_related_urls(query: str, max_results: int = 8) -> list[str]:
    """
    Searches the web for coverage of a claim using DuckDuckGo's HTML
    endpoint (no API key required, no AI model involved). Returns a
    list of result URLs reporting on the topic.
    """
    if not query.strip():
        return []
    try:
        response = requests.post(
            SEARCH_ENGINE_URL,
            data={"q": query},
            timeout=REQUEST_TIMEOUT,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 Chrome/151 Safari/537.36"
                )
            },
        )
        response.raise_for_status()
    except Exception as exc:
        logger.warning("Search engine request failed: %s", exc)
        return []

    try:
        soup = BeautifulSoup(response.text, "html.parser")
    except Exception as exc:
        logger.warning("Search result parsing failed: %s", exc)
        return []

    urls = []
    for link in soup.select("a.result__a, a.result__url"):
        href = link.get("href", "")
        parsed = urlparse(href)
        # DuckDuckGo HTML wraps outbound links in a redirect param; unwrap it.
        if parsed.netloc == "" and "uddg=" in href:
            qs = parse_qs(parsed.query)
            real = qs.get("uddg", [""])[0]
            if real:
                href = unquote(real)
        if href.startswith("http") and href not in urls:
            urls.append(href)
        if len(urls) >= max_results:
            break

    return urls

def domain_reputation(hostname: str) -> Optional[str]:
    if not hostname:
        return None
    h = hostname.lower()
    for trusted in TRUSTED_NEWS_DOMAINS:
        if h == trusted or h.endswith("." + trusted):
            return "trusted"
    if any(p in h for p in SHADY_NEWS_PATTERNS):
        return "shady"
    return None

@app.get("/")
def root():
    return {
        "service": "TrustGuard ML Service",
        "version": "5.2.1",
        "status": model_status(),
    }

@app.get("/health")
def health():
    status = model_status()
    return {
        "success": True,
        "status": "UP",
        "modelsReady": status["totalActive"] > 0,
        "models": status,
    }

@app.get("/models/status")
def models_status():
    return model_status()

@app.post("/analyze/news")
def analyze_news(payload: NewsPayload, x_gemini_api_key: Optional[str] = Header(default=None)):
    
    
    headline = clean_text(payload.headline)
    article_url = clean_text(payload.article_url)
    article_text = clean_text(payload.article_text)

    if not headline and not article_text:
        headline = clean_text(payload.text)

    if not headline and not article_url and not article_text:
        raise HTTPException(
            status_code=400,
            detail="Provide a headline, article URL, or article text.",
        )

    extracted = {"title": "", "text": ""}
    if article_url:
        try:
            validate_public_url(article_url)
            article_url = normalize_url(article_url)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

        extracted = extract_article(article_url)
        if not headline:
            headline = extracted["title"]
        if not article_text:
            article_text = extracted["text"]

    content = "\n".join(
        x for x in [headline, article_text] if x
    )[:MAX_INPUT_CHARS]

   
    if len(content.strip()) < 15:
        raise HTTPException(
            status_code=400,
            detail="The supplied news content is too short for analysis.",
        )
    # --- Phase II-C: claim extraction (must run BEFORE temporal) -----
    structured_claim = None
    suggested_queries: list[str] = []
    try:
        structured_claim = build_structured_claim(headline, article_text)
        suggested_queries = claim_to_search_queries(structured_claim)
    except Exception as exc:
        logger.warning("[CLAIM] extraction failed, continuing without it: %s", exc)

    # --- Phase II-E: temporal classification (depends on the above) --
    temporal_assessment = None
    try:
        mentioned_dates = structured_claim.entities.dates if structured_claim else []
        temporal_assessment = classify_currentness(
            extracted.get("published_at"),
            mentioned_dates,
        )
    except Exception as exc:
        logger.warning("[TEMPORAL] classification failed, continuing without it: %s", exc)    


    # Gather every voter's prediction FIRST, then poll once. Each voter
    # is called exactly once -- a heuristic counted twice would silently
    # double its weight in the ensemble.
    predictions = []

    local = local_news_prediction(content)
    if local:
        predictions.append(local)

    predictions.extend(
        pretrained_text_predictions("news", content)
    )

    # Always-available zero-dependency stylometric voter -- keeps the
    # ensemble multi-model even when Kaggle/BERTPhish/Gemini are all down.
    heuristic_vote = heuristic_news_vote(headline, article_text, make_prediction)
    if heuristic_vote:
        predictions.append(heuristic_vote)
    predictions.extend(hf_news_predictions(content))

    style = classify_style(headline, article_text)

    # BUGFIX: this used to call check_article_url_trust(...) TWICE (once
    # as `url_trust`, then again immediately as `embedded_url_trust`) and
    # appended the "URL Trust Analysis" prediction under each call if the
    # URL looked untrustworthy -- silently double-counting that voter's
    # weight in the ensemble poll. It is now computed once and voted once.
    embedded_url_trust = check_article_url_trust(headline, article_text, article_url)
    if embedded_url_trust["anyUntrustworthy"]:
        predictions.append(
            make_prediction("URL Trust Analysis", "Fake", 0.7,
                             source="heuristic", weight=1.3)
        )

    # PIB fact-check — independent voter, runs regardless of URLs present.
    pib = pib_fact_check(headline, article_text)
    if pib.get("covered") and pib["label"] in {"Real", "Fake"}:
        predictions.append(
            make_prediction("PIB Fact Check", pib["label"], None,
                             source="pib", weight=1.5)
        )

    # Search-coverage trust — independent voter, only meaningful when the
    # article/headline supplied no links of its own to check directly.
        # Search-coverage trust — independent voter, only meaningful when the
    # article/headline supplied no links of its own to check directly.
    search_url_trust = None
    if not embedded_url_trust["checked"]:
        search_url_trust = search_based_url_trust(headline, article_text)
        if search_url_trust.get("coverageFound"):
            total = search_url_trust["totalChecked"]
            trust_ratio = search_url_trust["trustedCount"] / total if total else 0
            
            if total >= 3:
                if trust_ratio >= 0.6:
                    predictions.append(
                        make_prediction("Search Coverage Trust", "Real",
                                         trust_ratio, source="heuristic", weight=1.2)
                    )
                elif trust_ratio <= 0.35:
                    predictions.append(
                        make_prediction("Search Coverage Trust", "Fake",
                                         1 - trust_ratio, source="heuristic", weight=1.2)
                    )
        

    # Gemini is an independent verification voter only when it actually
    # returns a classification. It does not receive fake confidence.
    gemini = gemini_news_check(
        headline,
        article_url,
        article_text,
        x_gemini_api_key,
    )
    if gemini["label"] in {"Real", "Fake"}:
        predictions.append(
            make_prediction(
                "Gemini + Google Search",
                gemini["label"],
                None,
                source="gemini",
            )
        )

    related_articles = search_related_articles(headline or content[:120], extract_article)
    cross_check = cross_check_related(content, related_articles, local_news_prediction)

    cross_check_weight = 0.6 if gemini["available"] else 1.0

    for vote in cross_check["crossCheckVotes"]:
        predictions.append(
            make_prediction(
                f"Cross-check: {vote['sourceTitle'][:40]}",
                vote["label"],
                vote.get("confidence"),
                source="cross_check",
                weight=cross_check_weight,
            )
        )
    poll = model_poll(predictions, "Fake News")
    winner = poll["winner"]

    badge = (
        "success" if winner == "Real"
        else "danger" if winner == "Fake"
        else "warning"
    )

    # "Related sources" falls back to a free DuckDuckGo search -- but only
    # once, and only when Gemini genuinely found nothing, so a user
    # without a Gemini key still gets related links.
    related_sources = gemini["sources"] or [
        {"title": a["title"], "url": a["url"]} for a in related_articles
    ]
    related_evidence = None
    try:
        related_evidence = collect_related_articles(suggested_queries, primary_label=poll["winner"])
    except Exception as exc:
        logger.warning("[EVIDENCE] related evidence collection failed: %s", exc)
    python_synthesis = None
    try:
        python_synthesis = synthesize(
            poll=poll,
            temporal=temporal_assessment.to_dict() if temporal_assessment else None,
            clickbait=structured_claim.clickbait if structured_claim else None,
            gemini_available=gemini["available"],
        )
    except Exception as exc:
        logger.warning("[SYNTHESIS] failed, continuing without it: %s", exc)



    return {
        "success": True,
        "label": winner,
        "confidence": poll["confidence"],
        "badgeClass": badge,
        "metrics": {
            "modelVotes": poll["votes"],
            "weightedVotes": poll["weightedVotes"],
            "totalModels": poll["totalVotes"],
            "participatingModels": [
                p["model"] for p in predictions
            ],
        },
        "explanation": (
            f"{poll['winningVotes']} of {poll['totalVotes']} "
            f"participating voters selected {winner}."
            if winner != "Unknown"
            else "No model produced a usable result."
        ),
        "poll": poll,
        "models": predictions,
        "crossCheck": cross_check,
        "styleAssessment": style,
        "input": {
            "headline": headline,
            "articleUrl": article_url,
            "articleExtracted": bool(extracted["text"]),
            "articleExtractionError": extracted.get("errorMessage"),
        },
        "webVerification": {
            "available": gemini["available"],
            "mode": gemini.get("mode", "gemini"),
            "vote": gemini["label"],
            "explanation": gemini["explanation"],
            "sources": gemini["sources"],
        },
        "pibFactCheck": {
            "available": pib["available"],
            "covered": pib.get("covered", False),
            "vote": pib["label"],
            "explanation": pib["explanation"],
            "sources": pib.get("sources", []),
        },
        "urlTrust": {
            "embedded": embedded_url_trust,
            "searchBased": search_url_trust,
        },
        "relatedNews": related_sources,
        "claim": structured_claim.to_dict() if structured_claim else None,
        "temporal": temporal_assessment.to_dict() if temporal_assessment else None,
        "suggestedSearchQueries": suggested_queries,
        "pythonSynthesis": python_synthesis.to_dict() if python_synthesis else None,
        "relatedEvidence": related_evidence,
        
    }

@app.post("/analyze/review")
def analyze_review(payload: TextPayload):
    content = clean_text(payload.text)
    if len(content) < 10:
        raise HTTPException(
            status_code=400,
            detail="Review must contain at least 10 characters.",
        )

    predictions = []

    local = local_review_prediction(content)
    if local:
        predictions.append(local)

    predictions.extend(
        pretrained_text_predictions("review", content)
    )

    # Always-available zero-dependency spam-pattern voter, called once.
    heuristic_vote = heuristic_review_vote(content, make_prediction)
    if heuristic_vote:
        predictions.append(heuristic_vote)

    poll = model_poll(predictions, "Fake Review")
    winner = poll["winner"]

    badge = (
        "success" if winner == "Genuine"
        else "danger" if winner == "Fake"
        else "warning"
    )

    fake_votes = poll["votes"].get("Fake", 0)
    spam_score = (
        fake_votes / poll["totalVotes"] * 100
        if poll["totalVotes"] else 0
    )

    return {
        "success": True,
        "label": winner,
        "confidence": poll["confidence"],
        "badgeClass": badge,
        "metrics": {
            "spamScore": round(spam_score, 1),
            "modelVotes": poll["votes"],
            "weightedVotes": poll["weightedVotes"],
            "totalModels": poll["totalVotes"],
            "participatingModels": [
                p["model"] for p in predictions
            ],
        },
        "explanation": (
            f"{poll['winningVotes']} of {poll['totalVotes']} "
            f"participating review voters selected {winner}."
            if winner != "Unknown"
            else "No compatible review model produced a result."
        ),
        "poll": poll,
        "models": predictions,
    }

@app.get("/models/registry")
def models_registry():
    return {"news": news_registry.as_config()}

@app.post("/analyze/review/page")
def analyze_review_page(payload: ReviewPagePayload):
    """Batch-analyze every review on a product page in one call, plus a
    simple check for suspicious rating-distribution skew (e.g. a pile of
    5-star ratings with little else -- a common review-bombing pattern)."""
    if not payload.reviews:
        raise HTTPException(status_code=400, detail="At least one review is required.")

    results = []
    for raw in payload.reviews[:100]:
        text = clean_text(raw)
        if len(text) < 10:
            continue
        try:
            result = analyze_review(TextPayload(text=text))
            results.append(result)
        except HTTPException:
            continue

    fake_count = sum(1 for r in results if r["label"] == "Fake")
    total = len(results)
    fake_ratio = fake_count / total if total else 0.0

    rating_skew = None
    if payload.ratings:
        numeric_ratings = [
            float(r)
            for r in payload.ratings
            if isinstance(r, (int, float)) and 0 <= float(r) <= 5
        ]
        if numeric_ratings:
            five_star_pct = sum(r >= 4.5 for r in numeric_ratings) / len(numeric_ratings)
            rating_skew = (
                "Suspicious (rating-bombed toward 5 stars)"
                if five_star_pct > 0.85
                else "Normal distribution"
            )

    verdict = (
        "Insufficient Review Data"
        if not results
        else "Likely Fake Reviews Present"
        if fake_ratio > 0.4
        else "Reviews Look Genuine"
    )

    return {
        "success": True,
        "reviewsAnalyzed": len(results),
        "fakeReviewCount": fake_count,
        "fakeReviewRatio": round(fake_ratio * 100, 1),
        "ratingPatternAssessment": rating_skew,
        "verdict": verdict,
        "details": results,
    }

@app.post("/analyze/phishing")
def analyze_phishing(payload: UrlPayload):
    url = normalize_url(payload.url)

    try:
        validate_public_url(url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    data = url_feature_data(url)

    predictions = []

    local = local_phishing_prediction(url)
    if local:
        predictions.append(local)

    predictions.extend(
        pretrained_phishing_predictions(url)
    )

    bert = bertphish_prediction(url)
    if bert:
        predictions.append(bert)

    # Standard checklist voter (typosquat / redirect chain / SSL / TLD) --
    # called exactly once. Its sub-signals are returned to the frontend
    # as `standardChecklist` regardless of which way it voted.
    checklist_vote, checklist = heuristic_phishing_vote(
        url, data["hostname"], bool(data["ssl"]), bool(data["shady_tld"]), make_prediction
    )
    if checklist_vote:
        predictions.append(checklist_vote)

    poll = model_poll(predictions, "Phishing")
    winner = poll["winner"]

    if winner == "Phishing":
        risk = (
            "High"
            if not data["ssl"] or data["shady_tld"]
            else "Medium"
        )
    elif winner == "Safe":
        risk = "Low"
    else:
        risk = "Unknown"

    badge = (
        "danger" if winner == "Phishing"
        else "success" if winner == "Safe"
        else "warning"
    )

    indicators = []
    if not data["ssl"]:
        indicators.append("HTTP connection")
    if data["shady_tld"]:
        indicators.append("suspicious TLD")
    if data["special_chars"] > 8:
        indicators.append("high special-character count")
    if "@" in url:
        indicators.append("@ symbol in URL")
    if data["hostname"] and data["hostname"].count(".") > 3:
        indicators.append("many subdomains")
    if checklist["typosquattingOf"]:
        indicators.append(f"looks like a typosquat of {checklist['typosquattingOf']}")
    if checklist["redirectHops"] >= 3:
        indicators.append(f"long redirect chain ({checklist['redirectHops']} hops)")

    # WHOIS lookups are a real network call, so they're opt-in
    # (ENABLE_DOMAIN_AGE_LOOKUP) rather than run on every request.
    domain_age = (
        domain_age_days(data["hostname"]) if ENABLE_DOMAIN_AGE_LOOKUP else None
    )

    return {
        "success": True,
        "label": winner,
        "confidence": poll["confidence"],
        "badgeClass": badge,
        "riskLevel": risk,
        "metrics": {
            "sslValid": bool(data["ssl"]),
            "domainAge": (
                f"{domain_age} days" if domain_age is not None else "Not checked"
            ),
            "tldTrust": (
                "Low" if data["shady_tld"]
                else "No obvious suspicious TLD"
            ),
            "specialCharCount": data["special_chars"],
            "modelVotes": poll["votes"],
            "weightedVotes": poll["weightedVotes"],
            "totalModels": poll["totalVotes"],
            "participatingModels": [
                p["model"] for p in predictions
            ],
        },
        "explanation": (
            "Indicators: " + ", ".join(indicators) + "."
            if indicators
            else (
                "No obvious structural phishing indicators were detected. "
                "A Safe result is not a guarantee that a website is trustworthy."
            )
        ),
        "poll": poll,
        "models": predictions,
        "url": url,
        "standardChecklist": {
            **checklist,
            "domainAgeDays": domain_age,
        },
    }

@app.post("/analyze/claim")
def analyze_claim(payload: ClaimPayload):
    claim = build_structured_claim(payload.headline, payload.article_text)
    return {
        "success": True,
        "claim": claim.to_dict(),
        "suggestedSearchQueries": claim_to_search_queries(claim),
    }

@app.get("/gemini/status")
def gemini_status():
    return {"success": True, "rotator": gemini_rotator.status()}
@app.post("/analyze/news/translate")
def translate_news(
    payload: TranslationPayload,
    x_gemini_api_key: Optional[str] = Header(default=None),
):
    prompt = f"""
Translate the following content into {payload.language}.
Preserve names, dates, organizations, places, numbers and factual meaning.
Do not add facts.

CONTENT:
{payload.text}
"""

    try:
        result = gemini_generate(prompt, x_gemini_api_key)
        return {"success": True, "language": payload.language, "translation": result, "source": "gemini"}
    except HTTPException:
        fallback = free_translate(payload.text, payload.language)
        if fallback:
            return {
                "success": True,
                "language": payload.language,
                "translation": fallback,
                "source": "free_translate_fallback",
            }
        raise HTTPException(
            status_code=503,
            detail=(
                "Translation is temporarily unavailable: Gemini failed and no "
                "backup translator is installed. Run `pip install deep-translator` "
                "to enable the offline-key-free backup."
            ),
        )


@app.post("/analyze/cluster")
def analyze_cluster(payload: ClusterPayload):
    articles = [
        ArticleForClustering(id=a.id, url=a.url, domain=a.domain, title=a.title)
        for a in payload.articles
    ]
    clusters = cluster_articles(articles)
    return {
        "success": True,
        "clusters": [c.to_dict() for c in clusters],
        "summary": independence_summary(clusters),
    }

@app.post("/analyze/temporal")
def analyze_temporal(payload: TemporalPayload):
    assessment = classify_currentness(payload.published_at or None, payload.mentioned_dates)
    return {"success": True, "temporal": assessment.to_dict()}
    
@app.post("/analyze/news/summary")
def summarize_news(
    payload: SummaryPayload,
    x_gemini_api_key: Optional[str] = Header(default=None),
):
    prompt = f"""
Summarize the following news in {payload.language}.

Return:
1. Short headline
2. Three key points
3. Important people/organizations
4. Important dates/numbers
5. Neutral summary
6. Uncertainty or missing context

Do not invent facts.

ARTICLE:
{payload.text}
"""

    try:
        result = gemini_generate(prompt, x_gemini_api_key)
        return {"success": True, "language": payload.language, "summary": result, "source": "gemini"}
    except HTTPException:
        # Gemini unavailable/failed — fall back to a dependency-free
        # extractive summary so the user still gets *something* useful.
        fallback = extractive_summary(payload.text, num_sentences=4)
        if payload.language.strip().lower() not in {"english", "en"}:
            translated = free_translate(fallback, payload.language)
            if translated:
                fallback = translated
            else:
                fallback += (
                    f"\n\n(Automatic translation to {payload.language} was unavailable; "
                    "showing an English extractive summary instead.)"
                )
        return {
            "success": True,
            "language": payload.language,
            "summary": fallback,
            "source": "extractive_fallback",
        }

def model_status():
    active = {
        "news": [],
        "review": [],
        "phishing": [],
    }

    if news_model is not None and news_vectorizer is not None:
        active["news"].append("Local News Model")

    if review_model is not None and review_vectorizer is not None:
        active["review"].append("Local Review Model")

    if phishing_model is not None:
        active["phishing"].append("Local Phishing Model")

    for item in pretrained_models:
        active[item["task"]].append(item["name"])

    if bertphish_model is not None:
        active["phishing"].append("BERTPhish")

    active["news"].append("Heuristic Style Check")
    active["review"].append("Heuristic Spam Pattern")
    active["phishing"].append("Standard Checklist (typosquat/redirects/SSL/TLD)")

    return {
        "active": active,
        "totalActive": sum(len(v) for v in active.values()),
        "local": {
            "news": news_model is not None and news_vectorizer is not None,
            "review": review_model is not None and review_vectorizer is not None,
            "phishing": phishing_model is not None,
        },
        "pretrained": len(pretrained_models),
        "pretrainedModels": [
            {
                "name": x["name"],
                "task": x["task"],
                "kind": x["kind"],
            }
            for x in pretrained_models
        ],
        "bertphish": bertphish_model is not None,
        "gemini": bool(GEMINI_API_KEY),
        "geminiModel": GEMINI_MODEL,
        "domainAgeLookupEnabled": ENABLE_DOMAIN_AGE_LOOKUP,
        "modelDirectory": str(MODELS_DIR),
        "pretrainedDirectory": str(PRETRAINED_DIR),
        "modelErrors": MODEL_ERRORS[-50:],
        "loadEvents": MODEL_LOAD_EVENTS[-100:],
        "newsRegistry": {
            "adapterCount": len(news_registry.for_task("news")),
        },
    }

@app.get("/analyze/health")
def analyze_health():
    return health()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=HOST,
        port=PORT,
        reload=RELOAD,
    )