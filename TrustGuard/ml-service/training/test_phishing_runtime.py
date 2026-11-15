"""Runtime-path test: load phishing_url_model_v2.joblib and run it through
the ACTUAL main.py functions (ast-extracted) that serve /analyze/phishing.
Measures end-to-end per-URL latency (feature extraction + predict) on this
machine."""
import ast
import logging
import os
import time

import joblib
import numpy as np

MAIN = os.path.expanduser("~/trust-guard/TrustGuard/ml-service/main.py")
MODEL = os.path.expanduser("~/trust-guard/TrustGuard/ml-service/models/phishing_url_model_v2.joblib")

text = open(MAIN).read()
tree = ast.parse(text)
wanted_fns = {"normalize_url", "clamp01", "make_prediction", "predict_model",
              "phishing_label", "url_feature_data", "phishing_features_for_model",
              "phishing_prediction_for_model", "local_phishing_prediction"}
segs = []
import ipaddress, re
from urllib.parse import urlparse
from typing import Any, Optional
ns = {"ipaddress": ipaddress, "re": re, "urlparse": urlparse, "Any": Any,
      "Optional": Optional, "np": np, "logger": logging.getLogger("t"),
      "os": os, "phishing_model": joblib.load(MODEL)}
for node in tree.body:
    if isinstance(node, ast.Assign) and any(
        getattr(t, "id", "") in {"SUSPICIOUS_KEYWORDS", "SHADY_TLDS", "DEFAULT_21_FEATURE_ORDER"} for t in node.targets):
        segs.append(ast.get_source_segment(text, node))
    elif isinstance(node, ast.FunctionDef) and node.name in wanted_fns:
        segs.append(ast.get_source_segment(text, node))
exec("\n\n".join(segs), ns)

model = ns["phishing_model"]
print("n_features_in_:", model.n_features_in_)
print("feature_names_in_:", list(model.feature_names_in_)[:5], "...")
predict = ns["local_phishing_prediction"]

cases = [
    ("https://www.google.com", "Safe"),
    ("https://github.com/Ayush1015/Trust-Guard", "Safe"),
    ("https://www.irctc.co.in/nget/train-search", "Safe"),
    ("http://verify-paypal-account-security.xyz/login", "Phishing"),
    ("http://secure-bank-update.info/login.php", "Phishing"),
    ("http://signin-google-account-verify.win/auth", "Phishing"),
    ("http://192.168.1.1/verify/account/login", "Phishing"),
    ("https://en.wikipedia.org/wiki/Phishing", "Safe"),
]
ok = 0
for url, expected in cases:
    r = predict(url)
    got = r["label"] if r else None
    mark = "OK " if got == expected else "?? "
    ok += got == expected
    print(f"{mark}{got:9s} conf={r['confidence'] if r else '-':>7} expected={expected:9s} {url}")
print(f"spot checks: {ok}/{len(cases)} as expected")

# latency: feature extraction + full prediction path, per URL, this machine
urls = [u for u, _ in cases] * 50
predict(urls[0])  # warm
t0 = time.perf_counter()
for u in urls:
    predict(u)
dt = (time.perf_counter() - t0) / len(urls) * 1000
print(f"end-to-end runtime path: {dt:.3f} ms/URL (n={len(urls)}, features+predict, this machine)")

# feature extraction alone
t0 = time.perf_counter()
for u in urls:
    ns["url_feature_data"](u)
dt2 = (time.perf_counter() - t0) / len(urls) * 1000
print(f"feature extraction only: {dt2:.3f} ms/URL")
