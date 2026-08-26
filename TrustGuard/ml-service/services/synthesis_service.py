"""
Phase II-H (partial): Python-only synthesis, independent of Gemini.

SCOPE: this reasons over signals from a SINGLE submitted article —
model poll, temporal status, clickbait score. It does NOT yet do
cross-article/cross-source evidence (that's §11/§12, not built yet).
Do not present its "why" as multi-source confirmation; it isn't.

This ALWAYS runs, regardless of whether Gemini succeeded, so:
  - When Gemini is available: its vote is already inside the poll
    (main.py adds it as a "Gemini + Google Search" prediction before
    calling model_poll()), and this module additionally reasons about
    temporal/clickbait context that the ML poll alone doesn't cover.
  - When Gemini is unavailable/exhausted: this is what fills the
    reasoning gap instead of silently shipping a bare REAL/FAKE label.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

# Matches §19's nuanced classification set exactly.
VALID_CLASSIFICATIONS = {
    "LIKELY TRUE", "MOSTLY TRUE", "MISLEADING", "OUTDATED", "RECYCLED",
    "UNVERIFIED", "LIKELY FALSE", "FALSE", "INSUFFICIENT EVIDENCE",
}

# Temporal statuses (from temporal_service.py) that indicate the
# content is being presented as newer than the evidence supports.
_STALE_TEMPORAL_STATUSES = {"OLD", "MISLEADINGLY_PRESENTED"}
_NO_SIGNAL_TEMPORAL_STATUSES = {"NO_RECENT_CONFIRMATION", "UNKNOWN"}


CLICKBAIT_HIGH_THRESHOLD = 60


@dataclass
class SynthesisResult:
    classification: str
    confidence: float  # 0-100
    basis: str  # "python_only" | "python_plus_gemini"
    reasoning: list[str] = field(default_factory=list)
    caveats: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "classification": self.classification,
            "confidence": round(self.confidence, 1),
            "reasoning": self.reasoning,
            "caveats": self.caveats,
            "basis": self.basis,
        }


def synthesize(
    poll: dict,
    temporal: Optional[dict] = None,
    clickbait: Optional[dict] = None,
    gemini_available: bool = False,
) -> SynthesisResult:
    """
    poll: the dict returned by main.py's existing model_poll().
    temporal: temporal_service.TemporalAssessment.to_dict(), or None.
    clickbait: structured_claim.clickbait dict (score + flags), or None.

    """
    reasoning: list[str] = []
    caveats: list[str] = []

    total_votes = poll.get("totalVotes", 0)
    winner = poll.get("winner", "Unknown")
    winning_votes = poll.get("winningVotes", 0)
    vote_confidence = poll.get("confidence", 0) or 0  # already 0-100 in model_poll()

    temporal_status = (temporal or {}).get("status")
    clickbait_score = (clickbait or {}).get("score", 0)

    basis = "python_plus_gemini" if gemini_available else "python_only"
    if not gemini_available:
        caveats.append(
            "Independent web verification (Gemini) was unavailable for this "
            "analysis. This assessment relies on ML classifiers and "
            "text-level heuristics only, not live source checking."
        )

    # --- 1. No usable votes at all ------------------------------------
    if total_votes == 0:
        reasoning.append("No model produced a usable prediction for this content.")
        return SynthesisResult("INSUFFICIENT EVIDENCE", 0.0, reasoning, caveats, basis)

    # --- 2. Temporal red flag: stale content presented as current -----
    if temporal_status in _STALE_TEMPORAL_STATUSES:
        for r in (temporal or {}).get("reasoning", []):
            reasoning.append(r)

        if winner == "Fake" and vote_confidence >= 60:
            reasoning.append(

                f"{winning_votes}/{total_votes} model votes classify this as Fake, "
                "consistent with stale/misrepresented content."
            )
            return SynthesisResult("FALSE", min(95, vote_confidence), reasoning, caveats, basis)

        reasoning.append(
            "The underlying event may be factually accurate, but the "
            "available signals suggest it is being presented as more "
            "current than the evidence supports."
        )
        # Confidence deliberately capped: this is a text-level heuristic,
        # not cross-source confirmation that the event is truly recycled.
        return SynthesisResult("OUTDATED", 55.0, reasoning, caveats, basis)

    # --- 3. Clickbait vs. underlying credibility separation (§8) -------
    if clickbait_score >= CLICKBAIT_HIGH_THRESHOLD:
        flags = (clickbait or {}).get("flags", {})
        hit_phrases = flags.get("sensational_phrases", [])
        if hit_phrases:
            reasoning.append(f"Headline uses sensational language: {', '.join(hit_phrases)}.")
        reasoning.append(f"Headline sensationalism score: {clickbait_score}/100.")

        if winner == "Real" and vote_confidence < 70:
            reasoning.append(
                f"Models lean Real ({winning_votes}/{total_votes} votes) but with "
                "moderate agreement, while the headline is highly sensational."
            )
            return SynthesisResult("MISLEADING", 50.0, reasoning, caveats, basis)

        if winner == "Fake":
            reasoning.append(f"{winning_votes}/{total_votes} model votes classify this as Fake.")
            return SynthesisResult("LIKELY FALSE", min(90, vote_confidence), reasoning, caveats, basis)


    # --- 4. No temporal/clickbait override: fall back to ML poll ------
    reasoning.append(f"{winning_votes} of {total_votes} participating models voted \"{winner}\".")

    if temporal_status in _NO_SIGNAL_TEMPORAL_STATUSES:
        caveats.append("No publish date or dated references were found to assess currentness.")

    if winner == "Real":
        if vote_confidence >= 80:
            return SynthesisResult("LIKELY TRUE", vote_confidence, reasoning, caveats, basis)
        if vote_confidence >= 55:
            return SynthesisResult("MOSTLY TRUE", vote_confidence, reasoning, caveats, basis)
        return SynthesisResult("UNVERIFIED", vote_confidence, reasoning, caveats, basis)

    if winner == "Fake":
        if vote_confidence >= 80:
            return SynthesisResult("FALSE", vote_confidence, reasoning, caveats, basis)
        if vote_confidence >= 55:
            return SynthesisResult("LIKELY FALSE", vote_confidence, reasoning, caveats, basis)
        return SynthesisResult("UNVERIFIED", vote_confidence, reasoning, caveats, basis)

    reasoning.append("Model votes were split with no clear majority.")
    return SynthesisResult("UNVERIFIED", vote_confidence, reasoning, caveats, basis)