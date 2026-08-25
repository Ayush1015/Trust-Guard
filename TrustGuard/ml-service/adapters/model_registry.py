"""
Phase II-A: Model Adapter Registry.

This wraps every EXISTING Phase I prediction function (local news model,
pretrained/Kaggle models, HF news classifiers, BERTPhish, Gemini) behind
a uniform contract, without changing what those functions do or how
analyze_news()/model_poll() work today.

Design choice: adapters wrap callables rather than re-implementing
prediction logic, so there is exactly one place (main.py's existing
predict_* functions) that owns model inference. This registry is
additive — it powers introspection (/models/registry) and gives future
phases (per-article voting, evidence engine) a uniform interface to
call against, but Phase I's own request path is untouched.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Optional


@dataclass
class ModelResult:
    model: str
    model_version: str
    status: str  # "success" | "failed"
    label: Optional[str]
    confidence: Optional[float]
    latency_ms: float

    timestamp: str
    metadata: dict = field(default_factory=dict)
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "model": self.model,
            "model_version": self.model_version,
            "status": self.status,
            "label": self.label,
            "confidence": self.confidence,
            "latency_ms": round(self.latency_ms, 2),
            "timestamp": self.timestamp,
            "metadata": self.metadata,
            "error": self.error,
        }


class ModelAdapter:
    """
    Wraps a single existing prediction function behind the Phase II
    contract. `predict_fn(content) -> dict | None` is expected to follow
    the existing Phase I convention: return a prediction dict
    (model/label/confidence/...) on success, or None on any failure.
    Phase I's predict_* functions already swallow their own exceptions
    and return None — we defensively catch anyway so a future adapter
    that DOES raise can never take down the registry.
    """

    def __init__(
        self,
        name: str,

        task: str,
        predict_fn: Callable[[str], Optional[dict]],
        version: str = "1.0",
        enabled: bool = True,
        supports: Optional[list[str]] = None,
        vote_enabled: bool = True,
    ):
        self.name = name
        self.task = task
        self.predict_fn = predict_fn
        self.version = version
        self.enabled = enabled
        self.supports = supports or ["headline", "article_text"]
        self.vote_enabled = vote_enabled

    def predict(self, content: str) -> ModelResult:
        timestamp = datetime.now(timezone.utc).isoformat()
        started = time.perf_counter()

        if not self.enabled:
            return ModelResult(
                model=self.name, model_version=self.version, status="failed",
                label=None, confidence=None, latency_ms=0.0,
                timestamp=timestamp, error="Model disabled in registry.",
            )

        error: Optional[str] = None
        raw: Optional[dict] = None
        try:
            raw = self.predict_fn(content)
        except Exception as exc:  # noqa: BLE001 - never let one model kill the batch
            error = f"{type(exc).__name__}: {exc}"


        latency_ms = (time.perf_counter() - started) * 1000

        if raw is None:
            return ModelResult(
                model=self.name, model_version=self.version, status="failed",
                label=None, confidence=None, latency_ms=latency_ms,
                timestamp=timestamp, error=error,
            )

        return ModelResult(
            model=self.name,
            model_version=self.version,
            status="success",
            label=raw.get("label"),
            confidence=raw.get("confidence"),
            latency_ms=latency_ms,
            timestamp=timestamp,
            metadata={"source": raw.get("source"), "weight": raw.get("weight")},
        )

    def as_config(self) -> dict:
        return {
            "name": self.name,
            "task": self.task,
            "version": self.version,
            "enabled": self.enabled,
            "supports": self.supports,
            "vote_enabled": self.vote_enabled,
        }



class ModelRegistry:
    def __init__(self):
        self._adapters: list[ModelAdapter] = []

    def clear(self):
        self._adapters = []

    def register(self, adapter: ModelAdapter):
        self._adapters.append(adapter)

    def for_task(self, task: str) -> list[ModelAdapter]:
        return [a for a in self._adapters if a.task == task and a.enabled]

    def run(self, task: str, content: str) -> list[ModelResult]:
        return [a.predict(content) for a in self.for_task(task)]

    def as_config(self) -> list[dict]:
        return [a.as_config() for a in self._adapters]