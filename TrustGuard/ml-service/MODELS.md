# Model & data artifacts - provenance and reproduction

This update adds no new model binaries or datasets. Pre-existing artifacts
remain unchanged; their provenance is not established by their presence.
See the root MODEL_NOTES.md for license and fresh-clone caveats. The
bootstrap/download scripts help obtain external artifacts; training outcomes
depend on dataset versions and optional augmentation, not exact reproduction.

| Artifact (runtime path) | Origin & license | Reproduce |
| --- | --- | --- |
| models/nli/* (NLI cross-encoder, ONNX) | cross-encoder/nli-MiniLM2-L6-H768, Apache-2.0 | `python training/bootstrap_nli.py` (downloads the official onnx/model_quint8_avx2.onnx + tokenizer; verified byte-identical to the artifacts used in testing) |
| models/phishing_url_model_v2.joblib | PhiUSIIL Phishing URL Dataset, UCI ML Repository 967, CC BY 4.0 (cite Prasad & Chandra 2024) | `python training/fetch_datasets.py` then `python training/train_phishing_v2.py` |
| models/review_model_v2.joblib | Salminen et al. 2022 (OSF, CC BY 4.0) via theArijitDas/Fake-Reviews-Dataset HF mirror (Apache-2.0) + Flowerly/modern-fake-reviews (CC BY 4.0) | `python training/fetch_datasets.py` then `python training/train_review_v2.py` (needs `pip install pyarrow`) |
| models/news_model_v2.joblib | Kaggle fake-news CSV - exact corpus/license UNVERIFIED | supply a licensed CSV via TG_NEWS_CSV, then `python training/train_news_v2.py`; the pre-existing cleaned_news.csv has unresolved provenance and should not be redistributed without permission |
| v1 joblibs (news/review/phishing) | owner's original Kaggle-era training, provenance unverified | not reproducible from public source; v2 models supersede them |
| 4 HF news classifiers (runtime, nothing bundled) | ThomasTschinkel/fake-news-detector MIT; akanbrown/AI-Fake_News_Detection_Roberta MIT; d-mistry013/fake-news-detector and dhruvpal/fake-news-bert NO license stated on their cards | auto-downloaded from HF Hub on first run; override list with HF_NEWS_MODELS |

Environment overrides: TG_NEWS_CSV, TG_PHIUSIIL_CSV, TG_DATA_DIR,
TG_MODELS_DIR, TG_LEGIT_URLS, HF_NEWS_MODELS, ENABLE_BERTPHISH (default
false; BERTPhish loads only from a user-supplied local directory).

Weak-label honesty: PhiUSIIL/Kaggle URL labels and the Kaggle news labels
are dataset-provided weak labels, not independently verified ground truth;
see root README.md and MODEL_NOTES.md for evaluation limits.

Full local run after artifacts: `uvicorn main:app --port 8778` (ML),
gateway with PYTHON_ML_SERVICE_URL=http://127.0.0.1:8778 on :5000, client
`npm run build`. JWT secret is required in production (hard-fail by design).
