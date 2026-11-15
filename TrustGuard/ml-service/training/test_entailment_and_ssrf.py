"""Unit tests for the entailment decision logic and SSRF URL guards.

No network and no ONNX model needed: _nli_batch is stubbed so the
decision thresholds in check_source() are tested directly, and
socket.getaddrinfo is stubbed for the DNS-rebinding guard.

Run:  python3 training/test_entailment_and_ssrf.py
"""

from __future__ import annotations

import os
import sys
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import services.entailment_service as nli  # noqa: E402

ARTICLE = (
    "Some navigation text here that is quite short. "
    "The central bank raised interest rates by half a percentage point on Tuesday. "
    "Analysts had widely expected the move after months of high inflation figures. "
    "Markets rose slightly after the announcement was made public."
)
CLAIM = "The central bank raised interest rates."


def stub_scores(entailment, neutral, contradiction):
    return {"entailment": entailment, "neutral": neutral, "contradiction": contradiction}


results = {}


def check(name, fn):
    try:
        fn()
        results[name] = "PASS"
    except AssertionError as exc:
        results[name] = f"FAIL: {exc}"


def t_supports():
    with mock.patch.object(nli, "is_available", return_value=True), \
         mock.patch.object(nli, "_nli_batch", return_value=[
             stub_scores(0.10, 0.85, 0.05),
             stub_scores(0.97, 0.02, 0.01),
             stub_scores(0.20, 0.70, 0.10),
         ]):
        r = nli.check_source(CLAIM, ARTICLE)
        assert r["verdict"] == "supports", r
        assert "central bank" in r["matchedPassage"], r
        assert r["available"] is True and r["sentencesChecked"] >= 2, r


def t_refutes():
    with mock.patch.object(nli, "is_available", return_value=True), \
         mock.patch.object(nli, "_nli_batch", return_value=[
             stub_scores(0.02, 0.03, 0.95),
             stub_scores(0.30, 0.60, 0.10),
         ]):
        r = nli.check_source(CLAIM, ARTICLE)
        assert r["verdict"] == "refutes", r


def t_split_signal_is_inconclusive():
    # one sentence strongly supports, another strongly refutes: no verdict
    with mock.patch.object(nli, "is_available", return_value=True), \
         mock.patch.object(nli, "_nli_batch", return_value=[
             stub_scores(0.97, 0.02, 0.01),
             stub_scores(0.01, 0.02, 0.97),
         ]):
        r = nli.check_source(CLAIM, ARTICLE)
        assert r["verdict"] == "inconclusive", r


def t_weak_signal_is_inconclusive():
    with mock.patch.object(nli, "is_available", return_value=True), \
         mock.patch.object(nli, "_nli_batch", return_value=[
             stub_scores(0.60, 0.35, 0.05),
         ]):
        r = nli.check_source(CLAIM, ARTICLE)
        assert r["verdict"] == "inconclusive", r


def t_model_unavailable():
    with mock.patch.object(nli, "is_available", return_value=False):
        r = nli.check_source(CLAIM, ARTICLE)
        assert r["verdict"] == "inconclusive" and r["available"] is False, r


def t_domain_dedupe():
    arts = [
        {"title": "A", "url": "https://site-a.com/1", "text": "x" * 200},
        {"title": "A2", "url": "https://site-a.com/2", "text": "y" * 200},
        {"title": "B", "url": "https://site-b.com/1", "text": "z" * 200},
    ]
    with mock.patch.object(nli, "is_available", return_value=True), \
         mock.patch.object(nli, "check_source", return_value={
             "verdict": "supports", "entailment": 0.9, "contradiction": 0.05,
             "neutral": 0.05, "matchedPassage": "p", "sentencesChecked": 3,
             "available": True,
         }):
        v = nli.verify_claim_against_articles(CLAIM, arts)
        assert len(v["sources"]) == 2, v  # second same-domain article dropped
        assert v["supports"] == 2, v


def t_predictions_mapping():
    def make_prediction(model, label, confidence, source=None, weight=1.0):
        return {"model": model, "label": label, "confidence": confidence,
                "source": source, "weight": weight}

    verification = {
        "sources": [
            {"verdict": "supports", "entailment": 0.9, "contradiction": 0.05,
             "title": "T1", "url": "https://a.com", "domain": "a.com",
             "matchedPassage": "p"},
            {"verdict": "refutes", "entailment": 0.1, "contradiction": 0.88,
             "title": "T2", "url": "https://b.com", "domain": "b.com",
             "matchedPassage": "q"},
            {"verdict": "inconclusive", "entailment": 0.4, "contradiction": 0.3,
             "title": "T3", "url": "https://c.com", "domain": "c.com",
             "matchedPassage": ""},
        ]
    }
    preds = nli.verification_to_predictions(verification, make_prediction)
    assert len(preds) == 2, preds  # inconclusive never votes
    assert preds[0]["label"] == "Real" and preds[1]["label"] == "Fake", preds
    assert all(p["evidenceType"] == "estimated_entailment" for p in preds), preds
    assert preds[0]["evidenceDetail"]["matchedPassage"] == "p", preds


# --- SSRF guards ------------------------------------------------------------

def t_validate_public_url():
    import main  # noqa: E402 - imports the real service module (no server start)

    blocked = [
        "http://127.0.0.1/admin",
        "http://localhost/",
        "http://169.254.169.254/latest/meta-data",
        "http://[::1]/",
        "http://10.0.0.5/internal",
        "http://192.168.1.1/router",
        "http://2130706433/",           # decimal 127.0.0.1
        "ftp://example.com/file",
        "http://example",               # dotless hostname
    ]
    for url in blocked:
        try:
            main.validate_public_url(url)
        except ValueError:
            continue
        raise AssertionError(f"should be blocked: {url}")

    # DNS rebinding: public-looking hostname resolving to a private IP.
    fake_private = [(2, 1, 6, "", ("10.9.9.9", 80))]
    with mock.patch("socket.getaddrinfo", return_value=fake_private):
        try:
            main.validate_public_url("http://rebind-attacker.example.com/")
        except ValueError:
            pass
        else:
            raise AssertionError("rebinding hostname should be blocked")

    fake_public = [(2, 1, 6, "", ("93.184.216.34", 80))]
    with mock.patch("socket.getaddrinfo", return_value=fake_public):
        main.validate_public_url("http://example.com/")


def t_safe_fetch_peer_guard():
    from services.safe_fetch import _is_disallowed_ip, safe_fetch_html

    assert _is_disallowed_ip("127.0.0.1")
    assert _is_disallowed_ip("169.254.169.254")
    assert _is_disallowed_ip("10.1.2.3")
    assert _is_disallowed_ip("::1")
    assert _is_disallowed_ip("fd00::1")
    assert not _is_disallowed_ip("93.184.216.34")

    # Redirect to a blocked destination must stop the fetch even when the
    # first hop is allowed: use a local redirect server with a validate_fn
    # that permits localhost but rejects link-local targets.
    import http.server
    import threading

    class Redirector(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(302)
            self.send_header("Location", "http://169.254.169.254/latest/meta-data")
            self.end_headers()

        def log_message(self, *args):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Redirector)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        def allow_local_validate(url):
            if "169.254.169.254" in url:
                raise ValueError("link-local blocked")

        # Peer-guard path: localhost connect allowed by validate_fn, but the
        # connected peer is loopback, so safe_fetch must still refuse.
        r = safe_fetch_html(f"http://127.0.0.1:{port}/", allow_local_validate)
        assert not r["ok"] if isinstance(r, dict) else not r.ok
        err = r["error"] if isinstance(r, dict) else r.error
        assert err == "ssrf_blocked", f"expected peer guard to block, got {err}"
    finally:
        server.shutdown()


for name, fn in list(globals().items()):
    if name.startswith("t_"):
        check(name, fn)

failed = {k: v for k, v in results.items() if v != "PASS"}
for k, v in results.items():
    print(f"{v if v != 'PASS' else 'PASS'} {k}" + (f" -> {v}" if v != "PASS" else ""))
print(f"\n{len(results) - len(failed)}/{len(results)} checks pass")
sys.exit(1 if failed else 0)
