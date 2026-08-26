"""
Phase II-E: Temporal / currentness classification.

SCOPE — read this before trusting the output:
This works from ONE article's own publish date + dates mentioned in
its own text. It can catch "this text discusses a 2016 event with no
recent corroborating date" (the recycled-news pattern from §5's
demonetisation example). It CANNOT yet do full §5 ("search current web,
find the latest related reporting") — that needs §10-12's multi-article
pipeline. Every status returned here has confidence="heuristic" for
that reason; do not present it to users as a stronger claim than that.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger("trustguard.temporal")

_HAS_DATEUTIL = False
try:
    from dateutil import parser as _dateutil_parser
    _HAS_DATEUTIL = True
except ImportError:
    logger.info(
        "[TEMPORAL] python-dateutil not installed — falling back to "
        "year-only date parsing. For full date parsing: "
        "pip install python-dateutil"

    )

_YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")
_RECENT_WORDS = {"today", "yesterday", "this week", "last week", "recently", "this year"}


def _parse_date_guess(text: str) -> Optional[datetime]:
    """Best-effort parse into a UTC datetime. Falls back to 'just the
    year, on Jan 1' when dateutil is missing or fails — good enough to
    bucket into CURRENT/RECENT/OLD, not precise for anything finer;
    callers must not treat the day/month as reliable in that fallback."""
    text = (text or "").strip()
    if not text:
        return None

    lower = text.lower()
    if lower in _RECENT_WORDS:
        return datetime.now(timezone.utc)

    if _HAS_DATEUTIL:
        try:
            parsed = _dateutil_parser.parse(text, fuzzy=True, default=datetime(1900, 1, 1))
            if parsed.year < 1990 or parsed.year > datetime.now().year + 1:
                return None
            return parsed.replace(tzinfo=timezone.utc)
        except Exception:
            pass

    match = _YEAR_RE.search(text)
    if match:
        try:
            return datetime(int(match.group()), 1, 1, tzinfo=timezone.utc)

        except ValueError:
            return None

    return None


@dataclass
class TemporalAssessment:
    status: str
    published_at: Optional[str]
    published_age_days: Optional[int]
    mentioned_event_year: Optional[int]
    reasoning: list = field(default_factory=list)
    confidence: str = "heuristic"

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "publishedAt": self.published_at,
            "publishedAgeDays": self.published_age_days,
            "mentionedEventYear": self.mentioned_event_year,
            "reasoning": self.reasoning,
            "confidence": self.confidence,
        }


def classify_currentness(
    published_at_raw: Optional[str],
    mentioned_dates: list[str],
    now: Optional[datetime] = None,
) -> TemporalAssessment:
    now = now or datetime.now(timezone.utc)

    reasoning: list[str] = []

    published_dt = _parse_date_guess(published_at_raw) if published_at_raw else None
    published_age_days = (now - published_dt).days if published_dt else None

    mentioned_years = [y for y in (_parse_date_guess(d) for d in mentioned_dates) if y]
    mentioned_years = [d.year for d in mentioned_years]

    # --- No signal at all ---
    if published_dt is None and not mentioned_years:
        reasoning.append("No publish date or dated references were found in the content.")
        return TemporalAssessment("NO_RECENT_CONFIRMATION", published_at_raw, None, None, reasoning)

    # --- Fresh publish date short-circuits to CURRENT/RECENT ---
    if published_dt is not None and published_age_days is not None:
        if published_age_days < 0:
            reasoning.append("Publish date is in the future relative to server time; treating as unreliable.")
        elif published_age_days <= 7:
            reasoning.append(f"Published {published_age_days} day(s) ago.")
            return TemporalAssessment("CURRENT", published_at_raw, published_age_days, None, reasoning)
        elif published_age_days <= 30:
            reasoning.append(f"Published {published_age_days} day(s) ago.")
            return TemporalAssessment("RECENT", published_at_raw, published_age_days, None, reasoning)

    # --- No fresh publish date: look for the old-event-presented-as-new
    # pattern in the article's own text. ---
    if mentioned_years:
        oldest_year = min(mentioned_years)
        newest_year = max(mentioned_years)
        clearly_historical = oldest_year < now.year - 1
        has_recent_reference = newest_year >= now.year - 1


        if clearly_historical and has_recent_reference:
            # Both an old origin AND a recent reference are present —
            # more likely a genuine update/reconfirmation than a
            # simple repost. Still heuristic: it means "this article's
            # own text mentions a recent year," not "independently
            # reconfirmed by another source" — that upgrade needs §10-12.
            reasoning.append(
                f"References an original event from {oldest_year}, but also "
                f"references {newest_year}, suggesting an update or "
                "reconfirmation rather than a simple repost."
            )
            return TemporalAssessment("UPDATED", published_at_raw, published_age_days, oldest_year, reasoning)

        if clearly_historical and not has_recent_reference:
            reasoning.append(
                f"References {oldest_year}, {now.year - oldest_year} year(s) before "
                "the current date, with no recent publish date or recent date "
                "reference found to corroborate a new event."
            )
            status = "MISLEADINGLY_PRESENTED" if published_dt is None else "OLD"
            return TemporalAssessment(status, published_at_raw, published_age_days, oldest_year, reasoning)

    if published_dt is not None:
        reasoning.append(f"Published {published_age_days} day(s) ago; no more specific signal available.")
        return TemporalAssessment("OLD", published_at_raw, published_age_days, None, reasoning)

    reasoning.append("Dated references found, but none clearly historical or clearly current.")
    return TemporalAssessment("UNKNOWN", published_at_raw, None, None, reasoning)