"""TrustGuard news model v2: retrain on committed cleaned_news.csv with
source-cue stripping, and quantify how much of the v1 performance came
from source cues (Reuters datelines) rather than content.

Honesty notes:
- Accuracy on a random split of THIS Kaggle dataset is not real-world
  accuracy; the dataset's provenance biases remain after cue stripping.
- We report both original-text and cue-stripped results, and a
  cross-condition eval (train stripped, test original, and vice versa).
"""
import json
import os
import re
import time
from pathlib import Path

import joblib
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score, classification_report
from sklearn.model_selection import train_test_split

ROOT = Path(__file__).resolve().parents[1]
# Override with TG_NEWS_CSV / TG_MODELS_DIR. The default CSV is a Kaggle
# fake-news export whose exact corpus and license are unverified (see
# MODELS.md); supply your own licensed CSV via TG_NEWS_CSV if needed.
CSV = os.getenv("TG_NEWS_CSV", str(ROOT / "cleaned_data" / "cleaned_news.csv"))
OUT = Path(os.getenv("TG_MODELS_DIR", str(ROOT / "models")))

CUE_PATTERNS = [
    r"\b(reuters|associated press|ap|afp|bloomberg|uptodate|upi|pti|ians|ani)\b\s*[-–—):]",
    r"^\s*[A-Z][A-Z\s,.']{2,30}\s*\((?:reuters|ap|afp)\)",  # DATELINE (Reuters)
    r"\((?:reuters|ap|afp)\)",
    r"\b(reuters|afp)\b",
]


def strip_cues(text: str) -> str:
    t = str(text)
    for pat in CUE_PATTERNS:
        t = re.sub(pat, " ", t, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", t).strip()


def make_vec():
    return TfidfVectorizer(stop_words="english", max_features=30000,
                           ngram_range=(1, 2), min_df=2, max_df=0.95,
                           sublinear_tf=True)


def make_model():
    return LogisticRegression(C=2.0, max_iter=2000, random_state=42)


def metrics(model, vec, X, y, tag):
    pred = model.predict(vec.transform(X))
    m = {
        "tag": tag,
        "accuracy": round(accuracy_score(y, pred), 4),
        "f1_weighted": round(f1_score(y, pred, average="weighted", zero_division=0), 4),
    }
    print(json.dumps(m))
    return m


df = pd.read_csv(CSV)
df = df.drop_duplicates(subset=["clean_text"]).reset_index(drop=True)
print("rows after dedupe:", len(df), dict(df["label"].value_counts()))

texts_orig = df["clean_text"].astype(str)
texts_stripped = texts_orig.map(strip_cues)
y = df["label"].values

Xtr_o, Xte_o, Xtr_s, Xte_s, ytr, yte = train_test_split(
    texts_orig, texts_stripped, y, test_size=0.2, random_state=42, stratify=y)

results = []

# v1-style: original text
vec_o, mod_o = make_vec(), make_model()
mod_o.fit(vec_o.fit_transform(Xtr_o), ytr)
results.append(metrics(mod_o, vec_o, Xte_o, yte, "v1_style_original_text"))

# v2: stripped text
vec_s, mod_s = make_vec(), make_model()
mod_s.fit(vec_s.fit_transform(Xtr_s), ytr)
results.append(metrics(mod_s, vec_s, Xte_s, yte, "v2_stripped_text"))

# cross-condition: v2 model on original text (cues present at inference)
results.append(metrics(mod_s, vec_s, Xte_o, yte, "v2_model_on_original_text"))
# v1 model on stripped text (how much did v1 lean on cues?)
results.append(metrics(mod_o, vec_o, Xte_s, yte, "v1_model_on_stripped_text"))

# latency: vectorize + predict, end-to-end per article
sample = Xte_s.iloc[:200].tolist()
vec_s.transform(sample[:1]); mod_s.predict_proba(vec_s.transform(sample[:1]))
t0 = time.perf_counter()
for t in sample:
    mod_s.predict_proba(vec_s.transform([t]))
dt = (time.perf_counter() - t0) / len(sample) * 1000
print(f"v2 vectorize+predict: {dt:.3f} ms/article (n=200, this machine)")

# cue reliance: accuracy using only the Reuters flag
import numpy as np
flag_tr = Xtr_o.str.contains("reuters", case=False).astype(int)
flag_te = Xte_o.str.contains("reuters", case=False).astype(int)
from sklearn.linear_model import LogisticRegression as LR
cue_only = LR(max_iter=1000, random_state=42).fit(flag_tr.values.reshape(-1, 1), ytr)
print("reuters-flag-only test accuracy:",
      round(accuracy_score(yte, cue_only.predict(flag_te.values.reshape(-1, 1))), 4))

# final artifacts: train on ALL data, stripped text
vec_f, mod_f = make_vec(), make_model()
mod_f.fit(vec_f.fit_transform(texts_stripped), y)
joblib.dump(mod_f, OUT / "news_model_v2.joblib")
joblib.dump(vec_f, OUT / "news_vectorizer_v2.joblib")
meta = {
    "artifacts": ["news_model_v2.joblib", "news_vectorizer_v2.joblib"],
    "trained_on": "committed cleaned_data/cleaned_news.csv (Kaggle fake-news dataset), "
                  "deduplicated, source-cue-stripped text",
    "cue_stripping_patterns": CUE_PATTERNS,
    "rows_after_dedupe": int(len(df)),
    "evaluation": results,
    "honesty": "random-split accuracy on this dataset is not real-world accuracy; "
               "dataset provenance bias remains after cue stripping",
    "sklearn_version": __import__("sklearn").__version__,
    "trained_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
}
(OUT / "news_model_v2_metadata.json").write_text(json.dumps(meta, indent=2))
print("saved news v2 artifacts + metadata")
