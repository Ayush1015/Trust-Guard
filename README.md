# Trust Guard

Collaborative React, Express and FastAPI project for news-claim analysis, review writing-origin estimates and URL structural-risk checks. Original contributors and history are preserved.

## November 15, 2026 source update

This repository contains the revised application code and regression tests. It is a **local demo**, not a published website or Chrome Web Store listing. Real news requests with web search took about 2-4.5 minutes in development. There is no millisecond end-to-end performance claim.

- News: model signals, estimated source support/refute with matched passages, and heuristic coverage groups. Coverage volume never votes that a claim is true. Vote-count ties abstain, including ties with unequal model confidence. Offline Gemini fallback is labelled as offline, not web verification.
- Reviews: estimates AI-generated versus human-written text. It does **not** detect deception, paid reviews or truthfulness.
- URLs: estimates risk from lexical/structural signals. It is not a malware scan or a safety guarantee. Redirect-based phishing inspection is unavailable. Public-article fetching separately uses guarded transport with per-hop URL checks.
- Chrome companion: on-demand page/selection preview with explicit checks, not continuous browsing capture. See [extension setup and privacy](trustguard-extension/README.md).

Model scores are uncalibrated estimates, not probabilities that an answer is correct. A repeated false claim can still look supported by a source-stance model. Missing sources, conflicting votes and weak evidence can produce Uncertain results.

## Source versus local model bundle

The code prefers v2 local models if present and falls back to older local artifacts when they are absent. **New v2 weights, the ONNX NLI model, tokenizer files and training datasets are not included in this source update.** A fresh clone is therefore not the same model profile as the separately supplied local demo package. Without the NLI files, source-stance checking is disabled rather than invented. Optional Hugging Face models may download at startup.

Pre-existing model/data files remain unchanged from the earlier repository; their presence is not a license verification. The old Kaggle news/cybersecurity data has unresolved provenance. Do not redistribute it or use it commercially without checking permission. Training scripts are development harnesses. `training/bootstrap_nli.py` downloads hash-checked NLI files; `training/fetch_datasets.py` fetches the documented review/phishing datasets. Retraining is separate, and optional URL augmentation changes the resulting model. Do not load untrusted pickle/joblib files.

See [local setup](SETUP_NOTES.txt) and [model/data notes](MODEL_NOTES.md). No API keys, new runtime databases, dependency directories or generated frontend builds are included in this update.

## Run locally

Requirements: Python 3.10/3.11, Node.js 22.12+ and npm.

1. In `TrustGuard/ml-service`, create a virtual environment and install `requirements.txt`. Local joblib artifacts in the demo were tested with scikit-learn 1.7.2. Run `python -m uvicorn main:app --host 127.0.0.1 --port 8000`.
2. In `trustguard-platform/server`, run `npm ci`, set `PYTHON_ML_SERVICE_URL=http://127.0.0.1:8000` and a private `JWT_SECRET`, then `npm start` (port 5000).
3. In `trustguard-platform/client`, run `npm ci` and `npm run dev` (port 5173).

Use separate terminals. Keep keys outside source control. Set `ENABLE_HF_NEWS_MODELS=false` and `ENABLE_SPACY_NER=false` for a reduced local profile; this changes available signals and is not an equivalent-accuracy mode.

## Tests

```sh
cd TrustGuard/ml-service
python training/test_model_poll.py
python training/test_news_voting_boundaries.py
python training/test_entailment_and_ssrf.py
python training/test_url_transport.py
# Requires local ONNX model files:
python training/test_nli_entailment.py
```

Gateway: `cd trustguard-platform/server && npm test`.
Frontend: `cd trustguard-platform/client && npm run build`.

Publication checks on November 15: poll regressions 13/13, gateway tests 5/5 and frontend production build passed. These are code regression checks, not broad detection-accuracy tests. Model-backed live checks were performed on the separate local demo profile, not on a fresh clone without its model bundle.

## Deployment limits

`Dockerfile` and `deploy/start.sh` are preparation only; a container deployment has not been verified. Production requires a private JWT secret, abuse controls, dependency updates and deployment testing. `PUBLIC_DEMO` disables accounts/history for ephemeral hosting. Local mode uses SQLite.

Compatible lockfile updates were checked on November 15: server production audit reports 0 advisories; 2 moderate development-only advisories remain in the nodemon chain. Client audit reports 0. Gateway regressions and frontend build pass after the updates. A complete live news-flow retest after these dependency updates is still outstanding. Deployment testing and abuse controls remain required; do not treat this demo as production-ready.
