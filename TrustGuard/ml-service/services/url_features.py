"""Canonical URL lexical feature extraction for phishing detection.

Shared by the FastAPI runtime (main.py) and the training script so that
train-time and serve-time features cannot drift apart. Pure stdlib.
"""

from __future__ import annotations

import ipaddress
import re
from typing import Any
from urllib.parse import urlparse

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

FEATURE_NAMES = (
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
)


def normalize_url(url: str) -> str:
    value = str(url or "").strip()
    if not value:
        return ""
    if not re.match(r"^https?://", value, re.I):
        value = "https://" + value
    return value


def compute_url_features(url: str) -> dict[str, Any]:
    """Return the 21 named lexical features plus supporting fields."""
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
        "feature_map": feature_map,
        "feature_vector": [float(feature_map[name]) for name in FEATURE_NAMES],
        "ssl": ssl,
        "special_chars": special_chars,
        "shady_tld": shady_tld,
        "hostname": host,
  }
