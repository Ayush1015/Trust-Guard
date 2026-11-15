"""Fetch a URL's HTML exactly once, safely, and hand it to callers so
extraction strategies (trafilatura, then BeautifulSoup fallback) never
issue duplicate network requests for the same page.

SECURITY: this module deliberately does NOT use requests' automatic
redirect-following. `validate_public_url()` (passed in as `validate_fn`)
blocks private/loopback/link-local IPs and localhost -- but that check is
worthless if a URL that passes validation then 302s to
http://169.254.169.254/ or http://localhost:8000/admin. Every redirect
hop is re-validated here before being followed, up to MAX_REDIRECTS.
"""

from __future__ import annotations

import ipaddress
import time
from dataclasses import dataclass
from typing import Callable, Optional
from urllib.parse import urljoin

import requests
from services.public_transport import public_session

MAX_REDIRECTS = 5
MAX_RESPONSE_BYTES = 8 * 1024 * 1024  # 8 MB
ALLOWED_CONTENT_TYPES = ("text/html", "application/xhtml+xml")


@dataclass
class FetchResult:
    ok: bool
    html: str = ""
    status_code: Optional[int] = None
    final_url: str = ""
    error: Optional[str] = None
    error_message: Optional[str] = None


_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    # requests' `text` decoding already handles gzip/deflate transparently.
    # We do NOT advertise brotli/zstd here: some servers send those even
    # when requests can't decode them cleanly, which is what corrupted
    # content when trafilatura's own fetcher was used directly.
    "Accept-Encoding": "gzip, deflate",
}


def _is_disallowed_ip(ip_str: str) -> bool:
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return False
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
    )


def _connected_peer_ip(response: requests.Response) -> Optional[str]:
    """Best-effort read of the actual TCP peer for a streamed response.
    Returns None when the socket is not introspectable (caller then relies
    on the pre-connect DNS validation, which still applies on every hop)."""
    try:
        connection = getattr(response.raw, "connection", None)
        sock = getattr(connection, "sock", None)
        if sock is None:
            return None
        peer = sock.getpeername()
        return peer[0] if peer else None
    except Exception:
        return None


def _read_capped(response: requests.Response, max_bytes: int) -> Optional[bytes]:
    """Reads the response body up to max_bytes. Returns None if the body
    exceeds the cap, so callers can reject oversized pages instead of
    buffering an attacker-controlled amount of memory."""
    chunks = []
    total = 0
    deadline = time.monotonic() + 30
    for chunk in response.iter_content(chunk_size=65536):
        if time.monotonic() > deadline:
            raise requests.exceptions.Timeout("Response body deadline exceeded")
        total += len(chunk)
        if total > max_bytes:
            return None
        chunks.append(chunk)
    return b"".join(chunks)


def safe_fetch_html(
    url: str,
    validate_fn: Callable[[str], None],
    timeout: int = 15,
    max_redirects: int = MAX_REDIRECTS,
    max_bytes: int = MAX_RESPONSE_BYTES,
) -> FetchResult:
    current_url = url

    for hop in range(max_redirects + 1):
        try:
            validate_fn(current_url)
        except ValueError as exc:
            return FetchResult(
                ok=False, final_url=current_url,
                error="ssrf_blocked" if hop > 0 else "invalid_url",
                error_message=str(exc),
            )

        try:
            response = public_session().get(
                current_url,
                timeout=timeout,
                headers=_HEADERS,
                allow_redirects=False,  # we validate + follow manually
                stream=True,
            )
        except ValueError as exc:
            return FetchResult(ok=False, final_url=current_url, error="ssrf_blocked", error_message=str(exc))
        except requests.exceptions.Timeout:
            return FetchResult(
                ok=False, final_url=current_url, error="timeout",
                error_message="The page took too long to respond.",
            )
        except requests.exceptions.SSLError as exc:
            return FetchResult(
                ok=False, final_url=current_url, error="ssl_error",
                error_message=f"SSL error: {exc}",
            )
        except requests.exceptions.RequestException as exc:
            return FetchResult(
                ok=False, final_url=current_url, error="fetch_failed",
                error_message=str(exc),
            )

        # Post-connect peer check: validate_public_url resolves DNS before
        # connecting, but DNS answers can change between that check and the
        # actual TCP connection (rebinding TOCTOU). Inspect the address we
        # actually connected to; a private/loopback peer means the page is
        # not a public website regardless of what the URL claimed.
        peer_ip = _connected_peer_ip(response)
        if peer_ip is not None and _is_disallowed_ip(peer_ip):
            response.close()
            return FetchResult(
                ok=False, final_url=current_url, error="ssrf_blocked",
                error_message="The server resolved to a private/local address.",
            )

        # Redirect: re-validate the *destination* before following it.
        if response.is_redirect or response.status_code in (301, 302, 303, 307, 308):
            location = response.headers.get("Location")
            response.close()
            if not location:
                return FetchResult(
                    ok=False, final_url=current_url, error="redirect_without_location",
                    error_message="Server returned a redirect with no Location header.",
                )
            current_url = urljoin(current_url, location)
            continue

        if response.status_code >= 400:
            error = "not_found" if response.status_code == 404 else "http_error"
            response.close()
            return FetchResult(
                ok=False, status_code=response.status_code, final_url=current_url,
                error=error, error_message=f"Server returned HTTP {response.status_code}.",
            )

        content_type = (response.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        if content_type and not any(content_type.startswith(ct) for ct in ALLOWED_CONTENT_TYPES):
            response.close()
            return FetchResult(
                ok=False, status_code=response.status_code, final_url=current_url,
                error="unsupported_content_type",
                error_message=f"Refusing to parse content-type '{content_type}'.",
            )

        raw = _read_capped(response, max_bytes)
        status_code = response.status_code
        encoding = response.encoding or "utf-8"
        response.close()

        if raw is None:
            return FetchResult(
                ok=False, status_code=status_code, final_url=current_url,
                error="too_large",
                error_message=f"Response exceeded the {max_bytes // (1024 * 1024)}MB size cap.",
            )

        try:
            html = raw.decode(encoding, errors="replace")
        except (LookupError, TypeError):
            html = raw.decode("utf-8", errors="replace")

        return FetchResult(ok=True, html=html, status_code=status_code, final_url=current_url)

    return FetchResult(
        ok=False, final_url=current_url, error="too_many_redirects",
        error_message=f"Exceeded the {max_redirects}-redirect limit.",
    )
