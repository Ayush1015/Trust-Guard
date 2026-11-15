"""TrustGuard review model v2.

Data (both free, license-verified on their HF dataset pages):
- Salminen et al. (2022) Fake Reviews Dataset (upstream OSF osf.io/tyue9, CC BY 4.0,
  verified via the OSF API license record), used through the
  theArijitDas/Fake-Reviews-Dataset HF mirror (Apache-2.0 processing):
  Salminen et al. / mexwell Kaggle "Fake Reviews" corpus - 20,294 GPT-2-era
  computer-generated fakes (label 1) + 20,232 genuine (label 0). This is the
  same corpus train_models.py cites, so it also enables the first honest
  evaluation of the COMMITTED review model on its own distribution.
- Flowerly/modern-fake-reviews (CC BY 4.0): modern LLM (DeepSeek-v4-pro)
  generated fakes paired on the same genuine half; per its card, detectors
  trained only on the GPT-2-era half catch ~4% of modern fakes.

Method:
- Normalize both to Fake/Genuine with a normalized-text key.
- Dedupe exact normalized texts; the two corpora SHARE the same genuine
  reviews, so split is grouped by normalized text: no text appears in both
  train and test.
- Held-out evaluation on the combined corpus PLUS dedicated cross-corpus
  evals: committed model and v2 on the Flowerly modern-fake test split.
"""
import hashlib
import json
import os
import re
import time
from pathlib import Path

import joblib
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.naive_bayes import MultinomialNB
from sklearn.metrics import (accuracy_score, f1_score, precision_score,
                             recall_score, roc_auc_score)
from sklearn.model_selection import GroupShuffleSplit

ROOT = Path(__file__).resolve().parents[1]
# Fetch inputs with training/fetch_datasets.py (licenses printed there) or
# override with TG_DATA_DIR / TG_MODELS_DIR.
DATA = os.getenv("TG_DATA_DIR", str(ROOT / "datasets"))
OUT = Path(os.getenv("TG_MODELS_DIR", str(ROOT / "models")))


def norm_key(t: str) -> str:
    t = re.sub(r"\s+", " ", str(t).lower()).strip()
    return hashlib.sha1(t.encode()).hexdigest()


a = pd.read_parquet(f"{DATA}/arijit_reviews.parquet")
a = pd.DataFrame({"text": a["text"].astype(str),
                  "y": (a["label"] == 1).astype(int),  # 1 = Fake (CG)
                  "source": "arijit_gpt2era"})
f_parts = []
for split in ("train", "validation", "test"):
    d = pd.read_parquet(f"{DATA}/flowerly_{split}.parquet")
    f_parts.append(pd.DataFrame({"text": d["text_"].astype(str),
                                 "y": (d["label"] == "CG").astype(int),
                                 "source": f"flowerly_{split}"}))
f = pd.concat(f_parts, ignore_index=True)

df = pd.concat([a, f], ignore_index=True)
df["key"] = df["text"].map(norm_key)
before = len(df)
df = df.drop_duplicates(subset=["key"]).reset_index(drop=True)
print(f"rows {before} -> {len(df)} after exact-text dedupe")
print(df.groupby(["source", "y"]).size())

# grouped split on normalized text (protects cross-corpus genuine overlap)
gss = GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=42)
tri, tei = next(gss.split(df[["text"]], df["y"], groups=df["key"]))
tr, te = df.iloc[tri], df.iloc[tei]
assert not set(tr["key"]) & set(te["key"])

vec = TfidfVectorizer(stop_words="english", max_features=60000,
                      ngram_range=(1, 2), min_df=2, max_df=0.95,
                      sublinear_tf=True)
Xtr = vec.fit_transform(tr["text"])
Xte = vec.transform(te["text"])


def report(model, X, y, tag):
    proba = model.predict_proba(X)
    classes = list(model.classes_)
    fi = classes.index(1)
    pred = model.predict(X)
    m = {
        "tag": tag,
        "accuracy": round(accuracy_score(y, pred), 4),
        "precision_fake": round(precision_score(y, pred, pos_label=1, zero_division=0), 4),
        "recall_fake": round(recall_score(y, pred, pos_label=1, zero_division=0), 4),
        "f1": round(f1_score(y, pred, zero_division=0), 4),
        "roc_auc": round(roc_auc_score(y, proba[:, fi]), 4),
    }
    print(json.dumps(m))
    return m


results = []

# 1. committed model baseline (same-distribution held-out + modern fakes)
committed_model = joblib.load(OUT / "review_model.joblib")
committed_vec = joblib.load(OUT / "review_vectorizer.joblib")
import warnings
warnings.filterwarnings("ignore")


def committed_predict_proba(texts):
    return committed_model.predict_proba(committed_vec.transform(texts))


def committed_metrics(texts, y, tag):
    proba = committed_predict_proba(texts)
    classes = list(committed_model.classes_)  # ['Fake','Genuine']
    fi = classes.index("Fake")
    pred = (proba[:, fi] >= 0.5).astype(int)
    m = {
        "tag": tag,
        "accuracy": round(accuracy_score(y, pred), 4),
        "recall_fake": round(recall_score(y, pred, pos_label=1, zero_division=0), 4),
        "precision_fake": round(precision_score(y, pred, pos_label=1, zero_division=0), 4),
        "roc_auc": round(roc_auc_score(y, proba[:, fi]), 4),
    }
    print(json.dumps(m))
    return m


modern_te = te[te["source"].str.startswith("flowerly")]
oldera_te = te[te["source"] == "arijit_gpt2era"]
results.append(committed_metrics(oldera_te["text"].tolist(), oldera_te["y"].values,
                                 "committed_model_on_gpt2era_heldout"))
results.append(committed_metrics(modern_te["text"].tolist(), modern_te["y"].values,
                                 "committed_model_on_modern_llm_heldout"))

# 2. v2 candidates on combined corpus
lr = LogisticRegression(C=2.0, max_iter=2000, random_state=42).fit(Xtr, tr["y"])
nb = MultinomialNB().fit(Xtr, tr["y"])
for name, m in (("logreg", lr), ("naive_bayes", nb)):
    results.append(report(m, Xte, te["y"].values, f"v2_{name}_combined_heldout"))
    results.append(report(m, vec.transform(modern_te["text"]), modern_te["y"].values,
                          f"v2_{name}_on_modern_llm_heldout"))
    results.append(report(m, vec.transform(oldera_te["text"]), oldera_te["y"].values,
                          f"v2_{name}_on_gpt2era_heldout"))

(OUT / "review_v2_eval.json").write_text(json.dumps(results, indent=2))

# pick by combined held-out f1, tiebreak modern recall
best = max([r for r in results if r["tag"].startswith("v2_") and "combined" in r["tag"]],
           key=lambda r: r["f1"])
kind = "logreg" if "logreg" in best["tag"] else "naive_bayes"
print("selected:", kind)

# latency of winner through vectorize+predict
winner = lr if kind == "logreg" else nb
sample = te["text"].iloc[:200].tolist()
vec.transform(sample[:1]); winner.predict_proba(vec.transform(sample[:1]))
t0 = time.perf_counter()
for t in sample:
    winner.predict_proba(vec.transform([t]))
print(f"v2 vectorize+predict: {(time.perf_counter()-t0)/len(sample)*1000:.3f} ms/review (n=200, this machine)")

# final artifacts: retrain on ALL combined data
vec_f = TfidfVectorizer(stop_words="english", max_features=60000,
                        ngram_range=(1, 2), min_df=2, max_df=0.95,
                        sublinear_tf=True)
Xf = vec_f.fit_transform(df["text"])
final = LogisticRegression(C=2.0, max_iter=2000, random_state=42) if kind == "logreg" else MultinomialNB()
final.fit(Xf, df["y"])
joblib.dump(final, OUT / "review_model_v2.joblib")
joblib.dump(vec_f, OUT / "review_vectorizer_v2.joblib")
meta = {
    "artifacts": ["review_model_v2.joblib", "review_vectorizer_v2.joblib"],
    "model_type": kind,
    "label_semantics": "classes Fake/Genuine; Fake probability drives the verdict",
    "trained_on": [
        "theArijitDas/Fake-Reviews-Dataset (Apache-2.0; mirror of Salminen et al. Kaggle corpus; GPT-2-era fakes)",
        "Flowerly/modern-fake-reviews (CC BY 4.0; DeepSeek-v4-pro fakes paired on the same genuine half)",
    ],
    "rows_after_exact_text_dedupe": int(len(df)),
    "split": "grouped by normalized text hash (the two corpora share genuine reviews); 80/20",
    "evaluation": results,
    "honesty": "held-out benchmark on these corpora, not a real-world fake-review catch rate; "
               "labels mean human-written vs AI-generated, not truthful vs deceptive",
    "sklearn_version": __import__("sklearn").__version__,
    "trained_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
}
(OUT / "review_model_v2_metadata.json").write_text(json.dumps(meta, indent=2))
print("saved review v2 artifacts + metadata")
