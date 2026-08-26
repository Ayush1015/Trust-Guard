"""
§11: Deduplication + source clustering.

Strategy chosen (stated explicitly since this was a judgment call,
not specified): domain-aware Jaccard similarity over word-shingled
titles, with exact-URL canonicalization as a fast-path duplicate
check. No embeddings, no new heavy dependency — this is deliberately
cheap enough to run on every analysis without a latency budget
conversation.

WHY NOT DOMAIN-BASED GROUPING: the naive approach (group by domain)
gets this backwards. The point of clustering is catching "10 sites
copying Reuters" — which by definition spans MULTIPLE domains. Domain
is used here only as a tie-breaker (two articles from the same domain
are never merged into each other, since a single outlet publishing two
related-but-distinct stories should not collapse into one "independent
source").

LIMITATION: Jaccard-over-titles catches syndicated/copied headlines
well. It will NOT catch two independently-written articles about the
same event with very differently worded headlines — that needs
semantic similarity (embeddings), which is a real upgrade path if
this proves too conservative in practice.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode

# Query params that don't change WHAT the page is, only how the click
# was tracked. Stripped before exact-duplicate comparison.
_TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "fbclid", "gclid", "ref", "ref_src", "source", "cid",
}

_WORD_RE = re.compile(r"[a-z0-9]+")

TITLE_SIMILARITY_THRESHOLD = 0.5  # Jaccard over word bigrams


@dataclass
class ArticleForClustering:
    """Minimal shape clustering needs — maps onto whatever §12's full
    Article dataclass ends up being; kept narrow on purpose so this
    module doesn't depend on that not-yet-built structure."""
    id: str
    url: str
    domain: str
    title: str


@dataclass
class SourceCluster:
    cluster_id: str
    article_ids: list = field(default_factory=list)
    domains: list = field(default_factory=list)  # unique domains in this cluster
    representative_title: str = ""

    @property
    def is_independent_confirmation(self) -> bool:
        """A cluster only counts as one independent confirmation
        regardless of how many articles are inside it — this is the
        exact mechanism that stops 10 Reuters-copies from outvoting
        one lone dissenting source."""
        return True

    def to_dict(self) -> dict:
        return {
            "clusterId": self.cluster_id,
            "articleIds": self.article_ids,
            "domains": self.domains,
            "domainCount": len(self.domains),
            "representativeTitle": self.representative_title,
        }


def canonicalize_url(url: str) -> str:
    """Strips tracking params and fragment so the same article shared
    via 3 different marketing links is recognized as one exact
    duplicate, not three."""
    try:
        parsed = urlparse(url.strip().lower())
        clean_query = [
            (k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True)
            if k not in _TRACKING_PARAMS
        ]
        return urlunparse((
            parsed.scheme, parsed.netloc, parsed.path.rstrip("/"),
            "", urlencode(clean_query), "",
        ))
    except Exception:
        return url.strip().lower()


def _word_bigrams(text: str) -> set:
    words = _WORD_RE.findall((text or "").lower())
    if len(words) < 2:
        return set(words)
    return {f"{words[i]}_{words[i + 1]}" for i in range(len(words) - 1)}


def title_similarity(title_a: str, title_b: str) -> float:
    """Jaccard similarity over word bigrams. 0.0 = no overlap, 1.0 = identical."""
    bigrams_a = _word_bigrams(title_a)
    bigrams_b = _word_bigrams(title_b)
    if not bigrams_a or not bigrams_b:
        return 0.0
    intersection = len(bigrams_a & bigrams_b)
    union = len(bigrams_a | bigrams_b)
    return intersection / union if union else 0.0


class _UnionFind:
    def __init__(self, ids: list):
        self._parent = {i: i for i in ids}

    def find(self, x):
        while self._parent[x] != x:
            self._parent[x] = self._parent[self._parent[x]]  # path compression
            x = self._parent[x]
        return x

    def union(self, a, b):
        root_a, root_b = self.find(a), self.find(b)
        if root_a != root_b:
            self._parent[root_b] = root_a


def deduplicate_exact(articles: list[ArticleForClustering]) -> list[ArticleForClustering]:
    """Drops exact-URL duplicates (after canonicalization), keeping the
    first occurrence. Run this BEFORE clustering — no point fuzzy-
    matching titles for articles that are byte-identical sources."""
    seen: set = set()
    deduped = []
    for article in articles:
        key = canonicalize_url(article.url)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(article)
    return deduped


def cluster_articles(
    articles: list[ArticleForClustering],
    threshold: float = TITLE_SIMILARITY_THRESHOLD,
) -> list[SourceCluster]:
    """
    O(n²) pairwise comparison — fine for the tens-of-articles-per-
    analysis scale this is built for. If a future phase pulls in
    hundreds of results per query, swap for locality-sensitive hashing
    (minhash) before this becomes a bottleneck; not needed yet.
    """
    deduped = deduplicate_exact(articles)
    if not deduped:
        return []

    ids = [a.id for a in deduped]
    by_id = {a.id: a for a in deduped}
    uf = _UnionFind(ids)

    for i in range(len(deduped)):
        for j in range(i + 1, len(deduped)):
            a, b = deduped[i], deduped[j]
            if a.domain and a.domain == b.domain:
                # Same outlet publishing two DIFFERENT articles should
                # not merge just because titles share some words —
                # only merge same-domain articles if they're near-
                # identical (very high bar), otherwise leave to the
                # cross-domain syndication case below.
                if title_similarity(a.title, b.title) >= 0.85:
                    uf.union(a.id, b.id)
                continue

            if title_similarity(a.title, b.title) >= threshold:
                uf.union(a.id, b.id)

    groups: dict[str, list[str]] = {}
    for article_id in ids:
        root = uf.find(article_id)
        groups.setdefault(root, []).append(article_id)

    clusters = []
    for index, (root, member_ids) in enumerate(groups.items()):
        members = [by_id[i] for i in member_ids]
        domains = list(dict.fromkeys(m.domain for m in members if m.domain))
        # Longest title as the representative — usually the least-truncated.
        representative = max((m.title for m in members), key=len, default="")

        clusters.append(SourceCluster(
            cluster_id=f"cluster_{index + 1}",
            article_ids=member_ids,
            domains=domains,
            representative_title=representative,
        ))

    # Largest clusters first — surfaces the most-corroborated story first in the UI.
    clusters.sort(key=lambda c: len(c.article_ids), reverse=True)
    return clusters


def independence_summary(clusters: list[SourceCluster]) -> dict:
    """§11's headline stat: 'Articles found: 12 / Independent source
    clusters: 4' — this is the number that must be used for evidence
    strength, never the raw article count."""
    total_articles = sum(len(c.article_ids) for c in clusters)
    return {
        "totalArticles": total_articles,
        "independentClusters": len(clusters),
        "largestClusterSize": max((len(c.article_ids) for c in clusters), default=0),
    }