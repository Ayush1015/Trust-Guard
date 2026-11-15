"""
Claim-level entailment checking with a local natural-language-inference
model.

What this does
--------------
For each fetched source article found during a news check, this module
estimates whether the article's text SUPPORTS, REFUTES, or is INCONCLUSIVE
about the submitted claim (usually the headline). It runs the claim against
the article sentence-by-sentence with a local ONNX NLI model and reports
the strongest matching passage.

Model: cross-encoder/nli-MiniLM2-L6-H768 (Apache-2.0, trained on
MultiNLI + SNLI), quantized ONNX export, runs on CPU, no API key, no
network. Model files are expected under models/nli/ next to the other
model artifacts (see training/test_nli_entailment.py for the grounded
sanity battery used to qualify it).

What this does NOT do (read before touching the callers)
--------------------------------------------------------
Entailment is TEXT COMPARISON, not fact verification:

- A source that repeats the same false claim still "supports" it.
- The model has no knowledge of the world; it only measures whether the
  source text implies or contradicts the claim text.
- MultiNLI/SNLI training is not FEVER-style fact verification; accuracy
  degrades on long, messy, sarcastic, or multi-claim text.
- Sentence-level matching can pick a passage that is about something
  else (entity/temporal mismatch).

Because of this, callers must:
- label results "estimated support / estimated refute / not verified",
  never "confirmed" or "debunked";
- cap all source-stance votes together to at most one ordinary voter;
- show the matched passage so a human can judge the match;
- deduplicate normalized hostnames, identical bodies and near-identical titles;
  this is only a copying heuristic, not proof of editorial independence.
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("trustguard.entailment")

_MODEL_DIR = Path(__file__).resolve().parent.parent / "models" / "nli"
_ONNX_FILE = _MODEL_DIR / "model_quint8_avx2.onnx"
_TOKENIZER_FILE = _MODEL_DIR / "tokenizer.json"
_CONFIG_FILE = _MODEL_DIR / "config.json"

# Decision thresholds. Deliberately strict: a weak or split signal must
# fall through to "inconclusive", not pick a side.
SUPPORT_THRESHOLD = 0.85
REFUTE_THRESHOLD = 0.85
MIN_MARGIN = 0.50  # winner must beat the other directional class by this much

MAX_SENTENCES_PER_ARTICLE = 48
MAX_SENTENCE_CHARS = 400
MAX_CLAIM_CHARS = 300

import threading
_INFERENCE_LOCK = threading.RLock()

_session = None
_tokenizer = None
_id2label: dict[int, str] = {}
_load_error: Optional[str] = None


def is_available() -> bool:
    """True when the NLI model loaded (or can load). Never raises."""
    if _load_error is not None:
        return False
    try:
        _ensure_loaded()
        return _session is not None
    except Exception:
        return False


def _ensure_loaded() -> None:
    with _INFERENCE_LOCK:
        _ensure_loaded_unlocked()


def _ensure_loaded_unlocked() -> None:
    global _session, _tokenizer, _id2label, _load_error
    if _session is not None or _load_error is not None:
        return
    try:
        import json

        import numpy as np  # noqa: F401  (import check only)
        import onnxruntime as ort
        from tokenizers import Tokenizer

        if not _ONNX_FILE.exists():
            _load_error = f"NLI model file missing: {_ONNX_FILE}"
            logger.warning("[NLI] %s - claim-level checks disabled.", _load_error)
            return

        cfg = json.loads(_CONFIG_FILE.read_text())
        _id2label = {int(k): v for k, v in cfg["id2label"].items()}
        _tokenizer = Tokenizer.from_file(str(_TOKENIZER_FILE))
        _session = ort.InferenceSession(
            str(_ONNX_FILE), providers=["CPUExecutionProvider"]
        )
        logger.info("[NLI] local entailment model loaded from %s", _ONNX_FILE)
    except Exception as exc:  # any load problem disables the voter, never the request
        _load_error = str(exc)
        logger.warning("[NLI] load failed (%s) - claim-level checks disabled.", exc)


def _split_sentences(text: str) -> list[str]:
    text = re.sub(r"\s+", " ", (text or "")).strip()
    if not text:
        return []
    parts = re.split(r"(?<=[.!?])\s+", text)
    sentences = []
    for part in parts:
        part = part.strip()
        # Skip navigation fragments, captions, wiki edit-markers, and
        # other tiny noise: they quote badly and match claims spuriously.
        if len(part) < 30 or "[edit]" in part or "[citation needed]" in part:
            continue
        sentences.append(part[:MAX_SENTENCE_CHARS])
        if len(sentences) >= MAX_SENTENCES_PER_ARTICLE:
            break
    return sentences


def _nli_batch(premises: list[str], hypothesis: str) -> list[dict[str, float]]:
    # Bound peak attention tensors and serialize this model's inference.
    # This is memory control, not an accuracy or public-capacity guarantee.
    with _INFERENCE_LOCK:
        out = []
        for start in range(0, len(premises), 4):
            out.extend(_score_nli_chunk(premises[start:start + 4], hypothesis))
        return out


def _score_nli_chunk(premises: list[str], hypothesis: str) -> list[dict[str, float]]:
    """Score (premise, hypothesis) pairs. Returns one probs dict per premise:
    {'entailment': p, 'neutral': p, 'contradiction': p}."""
    import numpy as np

    _ensure_loaded()
    if _session is None or not premises:
        return [{} for _ in premises]

    encodings = [_tokenizer.encode(p, hypothesis) for p in premises]
    max_len = max(len(e.ids) for e in encodings)
    input_ids = np.zeros((len(encodings), max_len), dtype=np.int64)
    attention = np.zeros((len(encodings), max_len), dtype=np.int64)
    for i, enc in enumerate(encodings):
        input_ids[i, : len(enc.ids)] = enc.ids
        attention[i, : len(enc.attention_mask)] = enc.attention_mask

    inputs = {"input_ids": input_ids, "attention_mask": attention}
    input_names = {i.name for i in _session.get_inputs()}
    if "token_type_ids" in input_names:
        token_types = np.zeros((len(encodings), max_len), dtype=np.int64)
        for i, enc in enumerate(encodings):
            token_types[i, : len(enc.type_ids)] = enc.type_ids
        inputs["token_type_ids"] = token_types

    logits = _session.run(None, inputs)[0]
    out = []
    for row in logits:
        row = row - row.max()
        e = np.exp(row)
        probs = e / e.sum()
        out.append({_id2label[i]: float(probs[i]) for i in range(len(probs))})
    return out


def check_source(claim: str, article_text: str) -> dict[str, Any]:
    """Estimate one article's stance toward one claim.

    Returns verdict in {"supports", "refutes", "inconclusive"} with the
    winning probabilities and the passage that drove the decision.
    Never raises: model-unavailable and empty inputs yield
    verdict "inconclusive" with available=False.
    """
    claim = re.sub(r"\s+", " ", (claim or "")).strip()[:MAX_CLAIM_CHARS]
    base = {
        "verdict": "inconclusive",
        "entailment": 0.0,
        "contradiction": 0.0,
        "neutral": 0.0,
        "matchedPassage": "",
        "sentencesChecked": 0,
        "available": False,
    }
    if not claim or not article_text:
        return base
    if not is_available():
        return base

    sentences = _split_sentences(article_text)
    if not sentences:
        return base

    try:
        scores = _nli_batch(sentences, claim)
    except Exception as exc:
        logger.warning("[NLI] inference failed: %s", exc)
        return base

    # Per-sentence decisiveness first: a verdict comes from a passage
    # whose OWN probabilities are decisive (high winner, clear margin
    # over the other directional class). Comparing the global max
    # entailment against the global max contradiction across DIFFERENT
    # sentences would mix unrelated passages and deadlock on any article
    # that mentions rival or historical facts.
    support_passages: list[tuple[float, str]] = []
    refute_passages: list[tuple[float, str]] = []
    best_e, best_c, best_n = 0.0, 0.0, 0.0
    for sent, probs in zip(sentences, scores):
        if not probs:
            continue
        e = probs.get("entailment", 0.0)
        c = probs.get("contradiction", 0.0)
        n = probs.get("neutral", 0.0)
        best_e, best_c, best_n = max(best_e, e), max(best_c, c), max(best_n, n)
        if e >= SUPPORT_THRESHOLD and e - c >= MIN_MARGIN:
            support_passages.append((e, sent))
        elif c >= REFUTE_THRESHOLD and c - e >= MIN_MARGIN:
            refute_passages.append((c, sent))

    verdict = "inconclusive"
    matched = ""
    if support_passages and not refute_passages:
        verdict = "supports"
        matched = max(support_passages)[1]
    elif refute_passages and not support_passages:
        verdict = "refutes"
        matched = max(refute_passages)[1]
    # Both directions present -> conflicting passages -> inconclusive.

    return {
        "supportPassages": len(support_passages),
        "refutePassages": len(refute_passages),
        "verdict": verdict,
        "entailment": round(best_e, 4),
        "contradiction": round(best_c, 4),
        "neutral": round(best_n, 4),
        "matchedPassage": matched,
        "sentencesChecked": len(sentences),
        "available": True,
    }


def verify_claim_against_articles(
    claim: str,
    articles: list[dict[str, Any]],
    max_sources: int = 4,
) -> dict[str, Any]:
    """Run check_source over fetched articles, one vote per independent
    domain (syndicated copies must not stack). `articles` items need
    title/url/text; missing text is skipped, not treated as a failure.
    """
    claim = re.sub(r"\s+", " ", (claim or "")).strip()[:MAX_CLAIM_CHARS]
    result = {
        "available": is_available(),
        "model": "nli-MiniLM2-L6-H768 (local, ONNX)",
        "claim": claim,
        "sources": [],
        "supports": 0,
        "refutes": 0,
        "inconclusive": 0,
        "note": (
            "Estimated by comparing the claim text against each source's "
            "text with a local language model. A source that repeats a "
            "false claim still counts as 'supports' - this is not "
            "independent fact verification."
        ),
    }
    if not result["available"] or not claim:
        return result

    seen_domains: set[str] = set()
    seen_bodies: set[str] = set()
    seen_titles: list[str] = []
    import hashlib
    from services.clustering_service import title_similarity
    for art in articles:
        if len(result["sources"]) >= max_sources:
            break
        text = (art.get("text") or "").strip()
        url = art.get("url", "")
        if len(text) < 100:
            continue
        from urllib.parse import urlparse

        domain = (urlparse(url).hostname or "").lower().removeprefix("www.")
        title = re.sub(r"\s+", " ", art.get("title", "").lower()).strip()
        body_hash = hashlib.sha256(re.sub(r"\s+", " ", text.lower()).encode()).hexdigest()
        if body_hash in seen_bodies or (len(title) >= 20 and any(title_similarity(title, other) >= 0.7 for other in seen_titles)):
            continue
        if domain and domain in seen_domains:
            continue
        seen_bodies.add(body_hash)
        if title:
            seen_titles.append(title)
        check = check_source(claim, text)
        if not check["available"]:
            continue
        if domain:
            seen_domains.add(domain)
        entry = {
            "title": art.get("title", ""),
            "url": url,
            "domain": domain,
            "publishedAt": art.get("published_at") or art.get("publishedAt"),
            **check,
        }
        result["sources"].append(entry)
        result[
            {"supports": "supports", "refutes": "refutes"}.get(
                check["verdict"], "inconclusive"
            )
        ] += 1

    return result


def verification_to_predictions(
    verification: dict[str, Any],
    make_prediction,
    weight: float = 0.25,
) -> list[dict[str, Any]]:
    """Turn per-source verdicts into ensemble predictions.

    Supports -> vote Real (the claim is supported by that source's text).
    Refutes  -> vote Fake. Inconclusive sources do not vote at all.
    Each prediction carries evidenceType 'estimated_entailment' so the
    poll, UI and report can keep it distinct from both pure model votes
    and topical matches. Confidence is the winning NLI probability of
    the matched passage, expressed as a percentage per the
    make_prediction contract.
    """
    predictions = []
    sources = verification.get("sources", [])
    directional_count = sum(src.get("verdict") in {"supports", "refutes"} for src in sources)
    capped_weight = min(max(0.0, weight), 1.0 / max(1, directional_count))
    for src in sources:
        verdict = src.get("verdict")
        if verdict not in {"supports", "refutes"}:
            continue
        label = "Real" if verdict == "supports" else "Fake"
        prob = src["entailment"] if verdict == "supports" else src["contradiction"]
        title = (src.get("title") or src.get("domain") or "source")[:40]
        pred = make_prediction(
            f"Source check: {title}",
            label,
            round(prob * 100, 1),
            source="nli_evidence",
            weight=capped_weight,
        )
        pred["evidenceType"] = "estimated_entailment"
        pred["evidenceDetail"] = {
            "url": src.get("url", ""),
            "domain": src.get("domain", ""),
            "verdict": verdict,
            "matchedPassage": src.get("matchedPassage", ""),
        }
        predictions.append(pred)
    return predictions
