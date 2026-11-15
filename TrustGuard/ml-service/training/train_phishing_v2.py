"""Train TrustGuard phishing URL model v2 on the PhiUSIIL dataset.

Dataset: PhiUSIIL Phishing URL Dataset (UCI ML Repository, dataset 967),
CC BY 4.0 license. URL-only lexical features matching the runtime's
url_feature_data feature_map exactly (verified by test_url_features_parity).

Honest evaluation: dedupe URLs, then BOTH a random stratified split and a
domain-grouped split (domains appear in only one partition) are reported.
"""
import ast
import json
import os
import time
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (accuracy_score, average_precision_score, brier_score_loss,
                             f1_score, log_loss, precision_score, recall_score,
                             roc_auc_score)
from sklearn.model_selection import GroupShuffleSplit, train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline

ROOT = Path(__file__).resolve().parents[1]
# Fetch the dataset with training/fetch_datasets.py (UCI 967, CC BY 4.0) or
# override paths with the TG_* environment variables.
DATA = os.getenv("TG_PHIUSIIL_CSV", str(ROOT / "datasets" / "PhiUSIIL_Phishing_URL_Dataset.csv"))
SHARED = str(ROOT / "services" / "url_features.py")
MAIN = str(ROOT / "main.py")
OUT_DIR = Path(os.getenv("TG_MODELS_DIR", str(ROOT / "models")))

import sys
sys.path.insert(0, os.path.dirname(SHARED))
from url_features import FEATURE_NAMES, compute_url_features
from urllib.parse import urlparse as _up

# --- parity check: shared module vs main.py's url_feature_data ---
def load_main_fns():
    text = open(MAIN).read()
    tree = ast.parse(text)
    wanted = {"normalize_url", "url_feature_data"}
    segs = []
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            getattr(t, "id", "") in {"SUSPICIOUS_KEYWORDS", "SHADY_TLDS"} for t in node.targets):
            segs.append(ast.get_source_segment(text, node))
        elif isinstance(node, ast.FunctionDef) and node.name in wanted:
            segs.append(ast.get_source_segment(text, node))
    import ipaddress, re
    from urllib.parse import urlparse
    from typing import Any, Optional
    ns = {"ipaddress": ipaddress, "re": re, "urlparse": urlparse, "Any": Any, "Optional": Optional}
    exec("\n\n".join(segs), ns)
    return ns["url_feature_data"]

battery = [
    "https://www.google.com",
    "http://verify-paypal-account-security.xyz/login",
    "github.com",
    "http://192.168.1.1/admin.php?x=1&y=2",
    "https://sub.deep.example.co.uk/path/page.html?q=a#frag",
    "http://secure-bank-update.info/login.php",
    "https://www.southbankmosaics.com",
    "http://user@evil-site.top/@redirect",
    "HTTPS://EXAMPLE.COM/UPPER/Path",
    "example.com/path?a=b&c=d",
    "http://wallet-crypto-connect.click/index.html",
    "https://my--hyphen--site.net/x_y-z",
]
main_ufd = load_main_fns()
mismatches = 0
for u in battery:
    a = main_ufd(u)["feature_map"]
    b = compute_url_features(u)["feature_map"]
    if a != b:
        mismatches += 1
        diff = {k: (a[k], b[k]) for k in a if a[k] != b[k]}
        print("MISMATCH", u, diff)
print(f"feature parity battery: {len(battery) - mismatches}/{len(battery)} match")
assert mismatches == 0

# --- data ---
df = pd.read_csv(DATA)
print("raw rows:", len(df))
df = df.drop_duplicates(subset=["URL"]).reset_index(drop=True)
print("after URL dedupe:", len(df))
y = (1 - df["label"].astype(int)).values  # dataset: 1 = legitimate, 0 = phishing -> normalize to 1 = phishing

# --- augmentation: PhiUSIIL legitimate URLs are nearly all bare homepages
# (100% HTTPS, path_length ~ 0), so a model trained on it alone flags any
# real deep link as phishing. Add REAL legitimate deep URLs collected from
# public news sitemaps (see collect_legit_urls.py) so the legitimate class
# includes paths, queries and hyphens. Sources: bbc.com, theguardian.com,
# cnn.com, aljazeera.com, wired.com, arstechnica.com, indianexpress.com.
AUG_FILE = os.getenv("TG_LEGIT_URLS", str(ROOT / "datasets" / "legit_deep_urls.txt"))
aug_urls = []
if os.path.exists(AUG_FILE):
    pool = [u.strip() for u in open(AUG_FILE) if u.strip()]
    rng_aug = np.random.RandomState(42)
    take = min(100000, len(pool))
    aug_urls = list(rng_aug.choice(pool, size=take, replace=False))
    print(f"augmenting with {len(aug_urls)} real legit deep URLs from sitemaps")
aug_domains = [(_up(u).hostname or "").lower() for u in aug_urls]

# domains for grouped split
domains = df["URL"].map(lambda u: (_up(u if "://" in str(u) else "http://" + str(u)).hostname or "").lower()).tolist()
domains.extend(aug_domains)
domains = np.array(domains)

t0 = time.time()
all_urls = df["URL"].tolist() + aug_urls
X = pd.DataFrame(
    [compute_url_features(u)["feature_map"] for u in all_urls],
    columns=list(FEATURE_NAMES),
).astype(float)
y = np.concatenate([y, np.zeros(len(aug_urls), dtype=int)])
print(f"feature extraction: {time.time()-t0:.1f}s for {len(X)} rows")
print("final class balance (1=phishing):", dict(pd.Series(y).value_counts()))


def evaluate(model, Xtr, Xte, ytr, yte, tag):
    t0 = time.time()
    model.fit(Xtr, ytr)
    fit_s = time.time() - t0
    proba = model.predict_proba(Xte)[:, 1]
    pred = (proba >= 0.5).astype(int)
    t0 = time.time()
    model.predict_proba(Xte.iloc[:100])
    infer_ms_100 = (time.time() - t0) * 1000
    m = {
        "tag": tag,
        "fit_seconds": round(fit_s, 2),
        "accuracy": round(accuracy_score(yte, pred), 4),
        "precision": round(precision_score(yte, pred), 4),
        "recall": round(recall_score(yte, pred), 4),
        "f1": round(f1_score(yte, pred), 4),
        "roc_auc": round(roc_auc_score(yte, proba), 4),
        "avg_precision": round(average_precision_score(yte, proba), 4),
        "brier": round(brier_score_loss(yte, proba), 4),
        "log_loss": round(log_loss(yte, proba), 4),
        "infer_ms_per_100_urls": round(infer_ms_100, 2),
    }
    print(json.dumps(m))
    return m


results = []

# random stratified split
Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)
# domain-grouped split
gss = GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=42)
tri, tei = next(gss.split(X, y, groups=domains))
Xgtr, Xgte = X.iloc[tri], X.iloc[tei]
ygtr, ygte = y[tri], y[tei]
overlap = set(pd.Series(domains).iloc[tri]) & set(pd.Series(domains).iloc[tei])
print("domain overlap between grouped train/test:", len(overlap))

for tag, (a, b, c, d) in {
    "random_split": (Xtr, Xte, ytr, yte),
    "domain_grouped_split": (Xgtr, Xgte, ygtr, ygte),
}.items():
    results.append(evaluate(
        Pipeline([("sc", StandardScaler()), ("lr", LogisticRegression(C=2.0, max_iter=2000, random_state=42))]),
        a, b, c, d, f"logreg/{tag}"))
    results.append(evaluate(
        HistGradientBoostingClassifier(max_iter=300, learning_rate=0.1, random_state=42),
        a, b, c, d, f"hgb/{tag}"))
    results.append(evaluate(
        RandomForestClassifier(n_estimators=200, max_depth=16, class_weight="balanced", random_state=42, n_jobs=-1),
        a, b, c, d, f"rf/{tag}"))

(OUT_DIR / "phishing_v2_eval.json").write_text(json.dumps(results, indent=2))

# pick by domain-grouped ROC-AUC (the harder, more honest split), tiebreak Brier
best = max([r for r in results if "domain_grouped" in r["tag"]],
           key=lambda r: (r["roc_auc"], -r["brier"]))
print("selected:", best["tag"])

finalists = {
    "logreg": lambda: Pipeline([("sc", StandardScaler()), ("lr", LogisticRegression(C=2.0, max_iter=2000, random_state=42))]),
    "hgb": lambda: HistGradientBoostingClassifier(max_iter=300, learning_rate=0.1, random_state=42),
    "rf": lambda: RandomForestClassifier(n_estimators=200, max_depth=16, class_weight="balanced", random_state=42, n_jobs=-1),
}
kind = best["tag"].split("/")[0]
model = finalists[kind]()
model.fit(X, y)

OUT_DIR.mkdir(parents=True, exist_ok=True)
joblib.dump(model, OUT_DIR / "phishing_url_model_v2.joblib")
metadata = {
    "artifact": "phishing_url_model_v2.joblib",
    "model_type": best["tag"],
    "trained_on": "PhiUSIIL Phishing URL Dataset (UCI ML Repository dataset 967), CC BY 4.0",
    "rows_after_url_dedupe": int(len(X)),
    "features": list(FEATURE_NAMES),
    "feature_source": "services/url_features.py (parity-tested against main.py url_feature_data)",
    "label_semantics": "artifact normalized: 1 = phishing, 0 = legitimate (source dataset inverted: 1 = legitimate)",
    "evaluation": results,
    "selected_by": "domain-grouped split ROC-AUC",
    "sklearn_version": __import__("sklearn").__version__,
    "trained_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
}
(OUT_DIR / "phishing_url_model_v2_metadata.json").write_text(json.dumps(metadata, indent=2))
print("saved artifact + metadata")
