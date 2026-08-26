"""
Phase II-C: Claim extraction.

Two extraction paths, same non-fatal pattern as BERTPhish/HF models:

  1. spaCy NER, if `spacy` + a model are installed — proper PERSON/ORG/
     GPE/DATE/MONEY/PERCENT recognition.
  2. Regex/heuristic fallback — always available, zero extra installs.
     Less accurate (it can't reliably tell a person from an
     organization), so it puts ambiguous proper nouns in `misc` rather
     than guessing wrong and polluting search queries with a bad
     "person" that's actually a company name.

Nothing here is called from the existing analyze_news() request path
except to ADD a `claim` field to the response — no existing key is
touched, and this cannot fail analyze_news() since it's wrapped in a
try/except at the call site (see main.py integration below).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

logger = logging.getLogger("trustguard.claim")

_NLP = None
_SPACY_MODEL = "en_core_web_sm"


def _try_load_spacy():

    global _NLP
    try:
        import spacy
        _NLP = spacy.load(_SPACY_MODEL)
        logger.info("[CLAIM] spaCy model '%s' loaded.", _SPACY_MODEL)
    except Exception as exc:
        logger.info(
            "[CLAIM] spaCy unavailable (%s). Using regex-based entity "
            "extraction instead. For proper NER: "
            "pip install spacy && python -m spacy download %s",
            exc, _SPACY_MODEL,
        )
        _NLP = None


_try_load_spacy()


@dataclass
class ExtractedEntities:
    people: list = field(default_factory=list)
    organizations: list = field(default_factory=list)
    locations: list = field(default_factory=list)
    dates: list = field(default_factory=list)
    money: list = field(default_factory=list)
    percentages: list = field(default_factory=list)
    misc: list = field(default_factory=list)  # ambiguous proper nouns (regex path only)

    def to_dict(self) -> dict:
        return {
            "people": self.people,
            "organizations": self.organizations,

            "locations": self.locations,
            "dates": self.dates,
            "money": self.money,
            "percentages": self.percentages,
            "misc": self.misc,
        }


_MONEY_RE = re.compile(
    r"[$€£₹]\s?\d[\d,]*(?:\.\d+)?\s?(?:million|billion|trillion|crore|lakh)?",
    re.I,
)
_PERCENT_RE = re.compile(r"\d+(?:\.\d+)?\s?%")
_DATE_RE = re.compile(
    r"\b(?:\d{1,2}\s)?(?:January|February|March|April|May|June|July|"
    r"August|September|October|November|December)(?:\s\d{1,2})?,?\s\d{4}\b"
    r"|\b\d{4}-\d{2}-\d{2}\b"
    r"|\b(?:today|yesterday|this week|last week|this year|recently)\b",
    re.I,
)
# Conservative heuristic: 2-4 capitalized words in a row. False
# negatives are safer than false positives here since these feed
# search queries directly.
_PROPER_NOUN_RE = re.compile(r"\b(?:[A-Z][a-zA-Z.&'-]*\s?){2,4}")
_STOPWORD_STARTS = {"The", "A", "An", "This", "That", "These", "Those", "It", "In", "On", "At", "As"}


def _regex_extract(text: str) -> ExtractedEntities:
    dates = list(dict.fromkeys(m.strip() for m in _DATE_RE.findall(text)))
    money = list(dict.fromkeys(m.strip() for m in _MONEY_RE.findall(text)))
    percentages = list(dict.fromkeys(m.strip() for m in _PERCENT_RE.findall(text)))


    misc = []
    seen = set()
    for match in _PROPER_NOUN_RE.finditer(text):
        phrase = match.group().strip()
        first_word = phrase.split()[0] if phrase else ""
        if not phrase or len(phrase) < 4 or first_word in _STOPWORD_STARTS:
            continue
        if phrase not in seen:
            seen.add(phrase)
            misc.append(phrase)

    return ExtractedEntities(dates=dates, money=money, percentages=percentages, misc=misc[:12])


def _spacy_extract(text: str) -> ExtractedEntities:
    doc = _NLP(text[:5000])  # cap input for latency
    entities = ExtractedEntities()
    seen = set()

    label_map = {
        "PERSON": entities.people,
        "ORG": entities.organizations,
        "GPE": entities.locations,
        "LOC": entities.locations,
        "DATE": entities.dates,
        "MONEY": entities.money,
        "PERCENT": entities.percentages,
    }

    for ent in doc.ents:
        text_val = ent.text.strip()
        key = (ent.label_, text_val)

        if not text_val or key in seen:
            continue
        seen.add(key)
        label_map.get(ent.label_, entities.misc).append(text_val)

    return entities


def extract_entities(text: str) -> ExtractedEntities:
    text = (text or "").strip()
    if not text:
        return ExtractedEntities()

    if _NLP is not None:
        try:
            return _spacy_extract(text)
        except Exception as exc:
            logger.warning("[CLAIM] spaCy extraction failed, using regex fallback: %s", exc)

    return _regex_extract(text)


# ---------------------------------------------------------------------
# Headline sensationalism signal (§8) — deliberately separate from
# factuality. This is a cheap heuristic; a fuller scorer belongs with
# the evidence engine in a later phase.
# ---------------------------------------------------------------------

_SENSATIONAL_PHRASES = {
    "shocking", "breaking", "you won't believe", "secret", "exposed",
    "banned", "warning", "urgent", "outrage", "slams", "destroys",
    "goes viral", "everyone is talking about", "won't believe",

}


def clickbait_signal(headline: str) -> dict:
    headline = headline or ""
    lower = headline.lower()

    hits = [p for p in _SENSATIONAL_PHRASES if p in lower]
    all_caps_words = [w for w in headline.split() if len(w) > 3 and w.isupper()]
    exclamations = headline.count("!")

    score = min(100, len(hits) * 20 + len(all_caps_words) * 15 + exclamations * 10)

    return {
        "score": score,
        "flags": {
            "sensational_phrases": hits,
            "all_caps_words": all_caps_words,
            "exclamation_count": exclamations,
        },
    }


@dataclass
class StructuredClaim:
    raw_text: str
    entities: ExtractedEntities
    clickbait: dict
    has_explicit_time_reference: bool

    def to_dict(self) -> dict:
        return {

            "raw_text": self.raw_text,
            "entities": self.entities.to_dict(),
            "clickbait": self.clickbait,
            "has_explicit_time_reference": self.has_explicit_time_reference,
        }


def build_structured_claim(headline: str = "", article_text: str = "") -> StructuredClaim:
    combined = " ".join(x for x in [headline, (article_text or "")[:2000]] if x).strip()
    entities = extract_entities(combined)
    clickbait = clickbait_signal(headline)

    return StructuredClaim(
        raw_text=headline or (article_text or "")[:200],
        entities=entities,
        clickbait=clickbait,
        has_explicit_time_reference=bool(entities.dates),
    )


def claim_to_search_queries(claim: StructuredClaim) -> list:
    """Bridges into search_adapter.build_query_variants using entities
    actually extracted from THIS claim — never hard-coded topics."""
    from adapters.search_adapter import build_query_variants

    entity_terms = (
        claim.entities.people
        + claim.entities.organizations
        + claim.entities.locations
        + claim.entities.misc
    )
    return build_query_variants(claim.raw_text, entities=entity_terms[:6])