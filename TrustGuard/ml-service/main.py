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
from urllib.parse import urlparse

import joblib
import numpy as np
import requests
from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

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
)
from gemini_backup import GeminiKeyRotator, is_quota_error
from adapters.model_registry import ModelAdapter, ModelRegistry

# ---------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("trustguard")


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
PORT = int(os.getenv("PORT", "8000"))
RELOAD = os.getenv("RELOAD", "true").lower() == "true"
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "15"))
MAX_ARTICLE_CHARS = int(os.getenv("MAX_ARTICLE_CHARS", "30000"))
MAX_INPUT_CHARS = int(os.getenv("MAX_INPUT_CHARS", "100000"))

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.6-flash").strip()

GEMINI_API_KEYS = (
    [k.strip() for k in os.getenv("GEMINI_API_KEYS", "").split(",") if k.strip()]
    or ([GEMINI_API_KEY] if GEMINI_API_KEY else [])
)
gemini_rotator = GeminiKeyRotator(GEMINI_API_KEYS, cooldown_seconds=90)

# WHOIS domain-age lookups are a real network call with real latency, so
# they stay opt-in rather than firing on every phishing check by default.
ENABLE_DOMAIN_AGE_LOOKUP = os.getenv("ENABLE_DOMAIN_AGE_LOOKUP", "false").lower() == "true"

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

MODELS_DIR.mkdir(parents=True, exist_ok=True)
PRETRAINED_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------
# GLOBAL STATE
# ---------------------------------------------------------------------

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
# ---------------------------------------------------------------------
# APP
# ---------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    load_all_models()
    yield

app = FastAPI(
    title="TrustGuard ML Service",
    version="5.2.0",
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

# ---------------------------------------------------------------------
# SCHEMAS
# ---------------------------------------------------------------------

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

# ---------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------
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

# ---------------------------------------------------------------------
# MODEL LOADING
# ---------------------------------------------------------------------

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
    logger.info(
        "Models ready | news=%s review=%s phishing=%s pretrained=%d bertphish=%s hf_news=%d",
        bool(news_model is not None and news_vectorizer is not None),
        bool(review_model is not None and review_vectorizer is not None),
        phishing_model is not None,
        len(pretrained_models),
        bertphish_model is not None,
        len(hf_news_classifiers),
    )

# ---------------------------------------------------------------------
# LABELS / PREDICTIONS
# ---------------------------------------------------------------------

def news_label(value: Any) -> str:
    v = str(value).strip().lower()
    if v in {"fake", "false", "1", "fake news", "f"}:
        return "Fake"
    if v in {"real", "true", "0", "real news", "r"}:
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

# ---------------------------------------------------------------------
# PHISHING URL FEATURES
# ---------------------------------------------------------------------

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

# ---------------------------------------------------------------------
# BERTPHISH
# ---------------------------------------------------------------------

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
# ---------------------------------------------------------------------
# MODEL POLL
# ---------------------------------------------------------------------

def model_poll(predictions: list[dict[str, Any]], task: str):
    valid = [
        p for p in predictions
        if p
        and p.get("status") == "participated"
        and p.get("label") not in {None, "", "Unknown"}
    ]

    if not valid:
        return {
            "winner": "Unknown",
            "votes": {},
            "weightedVotes": {},
            "totalVotes": 0,
            "winningVotes": 0,
            "confidence": 0,
            "models": [],
            "task": task,
        }

    # Every model gets one vote. Confidence is a secondary weighted score,
    # not a replacement for the vote.
    votes = Counter(p["label"] for p in valid)
    weighted = {}
    for p in valid:
        label = p["label"]
        conf = clamp01(p.get("confidence"), 0.5)
        weight = max(0.1, float(p.get("weight", 1.0)))
        weighted[label] = weighted.get(label, 0.0) + conf * weight

    top = max(votes.values())
    leaders = [label for label, count in votes.items() if count == top]

    if len(leaders) == 1:
        winner = leaders[0]
    else:
        winner = max(leaders, key=lambda x: weighted.get(x, 0.0))

    winning_votes = votes[winner]
    vote_confidence = winning_votes / len(valid)

    return {
        "winner": winner,
        "votes": dict(votes),
        "weightedVotes": {
            k: round(v, 4) for k, v in weighted.items()
        },
        "totalVotes": len(valid),
        "winningVotes": winning_votes,
        "confidence": round(vote_confidence * 100, 2),
        "models": valid,
        "task": task,
    }

# ---------------------------------------------------------------------
# ARTICLE EXTRACTION
# ---------------------------------------------------------------------

def extract_article(url: str) -> dict[str, str]:
    url = normalize_url(url)
    try:
        validate_public_url(url)
    except ValueError as exc:
        logger.warning("Article URL validation failed: %s", exc)
        return {"title": "", "text": ""}

    try:
        import trafilatura

        downloaded = trafilatura.fetch_url(url)
        if downloaded:
            extracted = trafilatura.extract(
                downloaded,
                include_comments=False,
                include_tables=False,
            )
            metadata = trafilatura.extract_metadata(downloaded)
            title = metadata.title if metadata else ""
            if extracted:
                return {
                    "title": clean_text(title),
                    "text": clean_text(extracted)[:MAX_ARTICLE_CHARS],
                }
    except Exception as exc:
        logger.debug("Trafilatura failed: %s", exc)

    try:
        from bs4 import BeautifulSoup

        response = requests.get(
            url,
            timeout=REQUEST_TIMEOUT,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 Chrome/151 Safari/537.36"
                )
            },
        )
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        for tag in soup(["script", "style", "noscript", "svg"]):
            tag.decompose()

        title = soup.title.get_text(" ", strip=True) if soup.title else ""
        paragraphs = [
            p.get_text(" ", strip=True)
            for p in soup.find_all("p")
        ]
        paragraphs = [p for p in paragraphs if len(p) >= 30]

        return {
            "title": clean_text(title),
            "text": clean_text("\n".join(paragraphs))[:MAX_ARTICLE_CHARS],
        }
    except Exception as exc:
        logger.warning("Article extraction failed: %s", exc)
        return {"title": "", "text": ""}

# ---------------------------------------------------------------------
# GEMINI
# ---------------------------------------------------------------------
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

    attempts = max(1, len(GEMINI_API_KEYS)) if not request_key else 1

    for _attempt in range(attempts):
        client, key_used = get_gemini_client(request_key)
        if not client:
            break  # no usable key -- fall through to the offline path

        try:
            from google.genai import types

            tools = [types.Tool(google_search=types.GoogleSearch())]
            if article_url:
                tools.append(types.Tool(url_context=types.UrlContext()))

            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(tools=tools, temperature=0.1),
            )

            output = str(getattr(response, "text", "") or "").strip()
            match = re.search(r"LABEL\s*:\s*(REAL|FAKE|UNKNOWN)", output.upper())
            label = (
                "Real" if match and match.group(1) == "REAL"
                else "Fake" if match and match.group(1) == "FAKE"
                else "Unknown"
            )

            return {
                "available": True,
                "label": label,
                "explanation": output,
                "sources": extract_grounding_sources(response),
            }
        except Exception as exc:
            if key_used and is_quota_error(exc):
                logger.warning("Gemini key exhausted, rotating: %s", exc)
                gemini_rotator.mark_exhausted(key_used)
                continue  # try the next key
            # Non-quota Gemini error (bad request, network issue, etc.) --
            # still fall through to the offline path below rather than
            # giving up, since the goal is "always produce a verdict."
            logger.warning("Gemini news check failed, falling back to offline verification: %s", exc)
            break

    # Reached whenever Gemini wasn't usable at all: not configured, every
    # key rate-limited, or a non-quota failure above. Python does the
    # verification task itself instead of returning "unavailable."
    logger.info("Gemini unavailable for news verification -- using offline Python fallback.")
    return offline_news_verification(headline, article_text, extract_article, local_news_prediction)

    
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
# ---------------------------------------------------------------------
# ENDPOINTS
# ---------------------------------------------------------------------

@app.get("/")
def root():
    return {
        "service": "TrustGuard ML Service",
        "version": "5.2.0",
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
def analyze_news(
    payload: NewsPayload,
    x_gemini_api_key: Optional[str] = Header(default=None),
):
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

    # -----------------------------------------------------------------
    # Gather every voter's prediction FIRST, then poll once. Each voter
    # is called exactly once -- a heuristic counted twice would silently
    # double its weight in the ensemble.
    # -----------------------------------------------------------------
    predictions = []

    local = local_news_prediction(content)
    if local:
        predictions.append(local)

    predictions.extend(
        pretrained_text_predictions("news", content)
    )

    # Always-available zero-dependency stylometric voter -- keeps the
    # ensemble multi-model even when Kaggle/BERTPhish/Gemini are all down.
    predictions.append(
        heuristic_news_vote(headline, article_text, make_prediction)
    )
    predictions.extend(hf_news_predictions(content))
        # Independently search the web for other coverage of this story and
    # run the SAME local ML model against each one found. This is a real
    # second opinion from separate sources, not just a link list.

    style = classify_style(headline, article_text)
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
        },
        "webVerification": {
            "available": gemini["available"],
            "mode": gemini.get("mode", "gemini"),
            "vote": gemini["label"],
            "explanation": gemini["explanation"],
            "sources": gemini["sources"],
        },
        "relatedNews": related_sources,
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
    predictions.append(
        heuristic_review_vote(content, make_prediction)
    )

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

    total = len(results) or 1
    fake_count = sum(1 for r in results if r["label"] == "Fake")
    fake_ratio = fake_count / total

    rating_skew = None
    if payload.ratings:
        numeric_ratings = [r for r in payload.ratings if isinstance(r, (int, float))]
        if numeric_ratings:
            five_star_pct = sum(1 for r in numeric_ratings if r >= 4.5) / len(numeric_ratings)
            rating_skew = (
                "Suspicious (rating-bombed toward 5 stars)"
                if five_star_pct > 0.85
                else "Normal distribution"
            )

    verdict = "Likely Fake Reviews Present" if fake_ratio > 0.4 else "Reviews Look Genuine"

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
# ---------------------------------------------------------------------
# STATUS
# ---------------------------------------------------------------------

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
    }

@app.get("/analyze/health")
def analyze_health():
    return health()

# ---------------------------------------------------------------------
# START
# ---------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=HOST,
        port=PORT,
        reload=RELOAD,
    )
