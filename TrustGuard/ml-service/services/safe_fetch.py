"""
Hardens article fetching for extract_article().

Fixes, in order of how they showed up in production logs:

1. "invalid ZSTD file" / "empty HTML tree" — trafilatura.fetch_url()
   negotiates Accept-Encoding itself (including zstd/br). When a
   server mislabels its response, or the decoder isn't available, the
   still-compressed bytes get handed to the HTML parser as text. Fix:
   fetch with `requests`, requesting only encodings it can always
   decode (gzip, deflate), and hand the already-decoded text straight
   to trafilatura.extract() instead of trafilatura.fetch_url().

2. 403/429 from bot-blocking sites — fails clearly and immediately
   with a labeled reason instead of silently falling through to an
   empty result that looks like a parser bug.

3. SSRF via redirects — validate_public_url() in main.py only checked
   the ORIGINAL url; requests follows redirects by default, so a URL
   could 302 to an internal/private IP and bypass that check. This
   disables automatic redirects and re-validates every hop.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable, Optional

import requests

logger = logging.getLogger("trustguard.fetch")


MAX_REDIRECTS = 5
MAX_RESPONSE_BYTES = 8 * 1024 * 1024  # 8 MB
REQUEST_TIMEOUT = 15

SAFE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/128.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    # Deliberately NOT br/zstd: if this environment's decoder doesn't
    # match what the server actually sends, the body gets corrupted
    # before trafilatura ever sees it. gzip/deflate are always safe
    # with `requests`' built-in decompression.
    "Accept-Encoding": "gzip, deflate",
}

FETCH_ERROR_MESSAGES = {
    "blocked": "The source blocked automated access (bot protection).",
    "not_found": "The article page returned a 404 Not Found.",
    "invalid_content_type": "The URL did not return an HTML page.",
    "too_large": "The page exceeded the maximum allowed size.",
    "network_error": "A network error occurred while fetching the page.",
    "ssrf_blocked": "The URL or one of its redirects points to a disallowed address.",
}


@dataclass
class FetchResult:

    html: Optional[str]
    final_url: str
    status_code: Optional[int]
    error: Optional[str]

    @property
    def ok(self) -> bool:
        return self.html is not None and self.error is None

    @property
    def error_message(self) -> Optional[str]:
        return FETCH_ERROR_MESSAGES.get(self.error) if self.error else None


def safe_fetch_html(url: str, validate_url: Callable[[str], None]) -> FetchResult:
    """`validate_url` should raise ValueError on an unsafe URL — reuses
    main.py's existing validate_public_url() so there's exactly one
    definition of "safe URL" for the initial request AND every redirect."""

    current_url = url

    try:
        validate_url(current_url)
    except ValueError:
        return FetchResult(None, current_url, None, "ssrf_blocked")

    session = requests.Session()

    for _ in range(MAX_REDIRECTS + 1):
        try:
            response = session.get(
                current_url,

                headers=SAFE_HEADERS,
                timeout=REQUEST_TIMEOUT,
                allow_redirects=False,
                stream=True,
            )
        except requests.exceptions.RequestException as exc:
            logger.warning("[FETCH] Network error for %s: %s", current_url, exc)
            return FetchResult(None, current_url, None, "network_error")

        if response.status_code in (301, 302, 303, 307, 308):
            next_url = response.headers.get("Location", "")
            response.close()
            if not next_url:
                return FetchResult(None, current_url, response.status_code, "network_error")
            try:
                validate_url(next_url)
            except ValueError:
                logger.warning("[FETCH] Redirect to unsafe URL blocked: %s -> %s", current_url, next_url)
                return FetchResult(None, current_url, response.status_code, "ssrf_blocked")
            current_url = next_url
            continue

        if response.status_code in (403, 429):
            response.close()
            logger.info("[FETCH] %s returned %s — site is blocking automated access.", current_url, response.status_code)
            return FetchResult(None, current_url, response.status_code, "blocked")

        if response.status_code == 404:
            response.close()
            return FetchResult(None, current_url, 404, "not_found")

        if not response.ok:

            response.close()
            return FetchResult(None, current_url, response.status_code, "network_error")

        content_type = response.headers.get("Content-Type", "")
        if "html" not in content_type and "xml" not in content_type:
            response.close()
            return FetchResult(None, current_url, response.status_code, "invalid_content_type")

        body = bytearray()
        for chunk in response.iter_content(chunk_size=65536):
            body.extend(chunk)
            if len(body) > MAX_RESPONSE_BYTES:
                response.close()
                return FetchResult(None, current_url, response.status_code, "too_large")

        html_text = body.decode(response.encoding or "utf-8", errors="replace")
        response.close()
        return FetchResult(html_text, current_url, response.status_code, None)

    return FetchResult(None, current_url, None, "network_error")