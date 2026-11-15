# TrustGuard local training & test harnesses (local enhancement, Nov 2026)

Scripts here reproduce the v2 model artifacts in `../models/`. These are development harnesses with external dataset prerequisites.
bootstrap_nli.py downloads hash-checked NLI files; fetch_datasets.py fetches
review/phishing inputs. Training paths are repository-relative with TG_* overrides.
New weights/data are not committed. The old Kaggle news corpus has unresolved
provenance; do not assume download availability grants redistribution rights.
Run inside the ml-service directory with Python 3.10 + scikit-learn 1.7.2.

- `test_model_poll.py` - regression harness for the ensemble aggregation
  (`model_poll` in `../main.py`). Reproduces the pre-fix defect from a
  backup of the old function and verifies the fix. 11/11 checks.
- `collect_legit_urls.py` - collects REAL legitimate deep URLs (public news
  sitemaps) used to augment the phishing legitimate class. HN/Wikipedia/
  StackOverflow URLs were collected via their public JSON APIs.
- `train_phishing_v2.py` - trains `phishing_url_model_v2.joblib` on the
  PhiUSIIL dataset (UCI #967, CC BY 4.0) + legit deep URL augmentation.
  Includes the train/serve feature-parity battery.
- `train_news_v2.py` - trains `news_model_v2.joblib` with source-cue
  stripping; cross-condition evaluation; Reuters-flag leakage probe.
- `train_review_v2.py` - trains `review_model_v2.joblib` on
  theArijitDas/Fake-Reviews-Dataset (Apache-2.0) + Flowerly/modern-fake-reviews
  (CC BY 4.0), with grouped split and cross-corpus evals.
- `test_phishing_runtime.py` - runs the v2 phishing model through the actual
  runtime code path (ast-extracted from main.py) with a spot battery and
  latency measurement.

No new training datasets are added. Pre-existing cleaned_data files were left unchanged; their licensing remains unresolved. See root MODEL_NOTES.md.
