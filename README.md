# 🛡️ TrustGuard

### AI-Powered Multi-Signal Platform for News, Review & Phishing Verification

TrustGuard is a full-stack digital intelligence and verification platform that analyzes **news claims, product reviews, and URLs** using multiple independent machine-learning models, evidence sources, and security signals.

Instead of depending on a single AI model, TrustGuard combines:

* 🧠 Local machine-learning models
* 🤗 Hugging Face models
* 📦 Kaggle / pretrained models
* 🏛️ PIB Fact Check
* 🔍 Search Coverage Trust
* 🌐 URL and domain analysis
* 📰 Related article analysis
* 🔗 Source-independence clustering
* ⏱️ Temporal/currentness analysis
* ✨ Optional Gemini verification
* 🐍 Offline Python fallback verification
* ⚖️ Weighted ensemble voting
* 📡 Real-time Server-Sent Events (SSE)

The goal is to provide an **explainable, evidence-driven assessment** instead of treating one model's prediction as absolute truth.

---

# 📌 Table of Contents

* [Overview](#-overview)
* [Core Features](#-core-features)
* [System Architecture](#-system-architecture)
* [News Analysis](#-news-analysis)
* [PIB Fact Check](#-pib-fact-check)
* [Search Coverage Trust](#-search-coverage-trust)
* [Review Analysis](#-review-analysis)
* [Phishing Detection](#-phishing-detection)
* [Machine Learning Layer](#-machine-learning-layer)
* [Gemini Integration](#-gemini-integration)
* [Weighted Ensemble](#-weighted-ensemble)
* [Evidence Normalization](#-evidence-normalization)
* [Live SSE Analysis](#-live-sse-analysis)
* [Project Structure](#-project-structure)
* [Technology Stack](#-technology-stack)
* [Installation](#-installation)
* [Environment Configuration](#-environment-configuration)
* [Running the Application](#-running-the-application)
* [API Reference](#-api-reference)
* [Health & Diagnostics](#-health--diagnostics)
* [Security](#-security)
* [Reliability & Fallbacks](#-reliability--fallbacks)
* [Troubleshooting](#-troubleshooting)
* [Development Workflow](#-development-workflow)
* [Roadmap](#-roadmap)
* [Disclaimer](#-disclaimer)
* [License](#-license)

---

# 🔎 Overview

TrustGuard is designed around a simple principle:

> **Verification should be based on multiple independent signals rather than a single prediction.**

For example, if a news claim is classified as `Fake` by one ML model, TrustGuard does not automatically treat the claim as fake.

Instead, it can compare:

```text
Local ML
   +
Hugging Face
   +
Kaggle Model
   +
PIB Fact Check
   +
Search Coverage
   +
Related Articles
   +
Source Trust
   +
Temporal Analysis
   +
Optional Gemini
        │
        ▼
Weighted Evidence
        │
        ▼
Final Assessment
```

This architecture makes the system more resilient to:

* Incorrect ML predictions
* Missing models
* Search failures
* Gemini quota exhaustion
* Missing PIB coverage
* Conflicting evidence
* Unavailable external services

---

# ✨ Core Features

## 📰 News Verification

Analyze:

* News headlines
* Article URLs
* Article text
* Claims
* Currentness
* Related coverage

The news pipeline can combine:

* Local ML classifiers
* Hugging Face models
* Kaggle/pretrained models
* PIB Fact Check
* Search Coverage Trust
* URL analysis
* Related articles
* Source clustering
* Temporal classification
* Gemini verification
* Offline fallback

---

## ⭐ Review Analysis

Analyze product reviews for signals associated with:

* Genuine reviews
* Suspicious reviews
* Fake/repetitive reviews
* Review manipulation patterns

The review pipeline can combine:

```text
Local ML
   +
Kaggle / pretrained models
   +
Writing-style heuristics
   +
Ensemble voting
```

---

## 🔗 Phishing Detection

Analyze URLs for phishing and malicious characteristics.

Signals can include:

* URL structure
* Suspicious domains
* Domain characteristics
* Typosquatting
* IP-based URLs
* Suspicious paths
* Redirect patterns
* Security indicators
* Local ML
* Kaggle/pretrained models
* Optional BERTPhish

---

# 🏗️ System Architecture

```text
                         ┌──────────────────────────────┐
                         │       REACT FRONTEND         │
                         │            Vite              │
                         │                              │
                         │  • News Analysis             │
                         │  • Review Analysis            │
                         │  • Phishing Analysis         │
                         │  • Live Progress / Results   │
                         └──────────────┬───────────────┘
                                        │
                         REST API ──────┼────── SSE
                                        │
                                        ▼
                         ┌──────────────────────────────┐
                         │       NODE.JS API            │
                         │       EXPRESS GATEWAY        │
                         │                              │
                         │  • API Routing               │
                         │  • Request Validation        │
                         │  • CORS / Security           │
                         │  • Python Service Proxy      │
                         │  • SSE Streaming             │
                         └──────────────┬───────────────┘
                                        │
                                        │ HTTP / REST
                                        ▼
                         ┌──────────────────────────────┐
                         │      PYTHON ML SERVICE       │
                         │       FASTAPI / UVICORN      │
                         │                              │
                         │  • Model Orchestration       │
                         │  • Evidence Collection       │
                         │  • Ensemble Voting           │
                         │  • News Verification         │
                         │  • Review Classification     │
                         │  • Phishing Detection        │
                         └──────────────┬───────────────┘
                                        │
                 ┌──────────────────────┼──────────────────────┐
                 │                      │                      │
                 ▼                      ▼                      ▼
       ┌──────────────────┐   ┌──────────────────┐   ┌──────────────────┐
       │   📰 NEWS        │   │   ⭐ REVIEW      │   │  🔗 PHISHING     │
       │    ANALYSIS      │   │    ANALYSIS      │   │    ANALYSIS      │
       └────────┬─────────┘   └────────┬─────────┘   └────────┬─────────┘
                │                      │                      │
        ┌───────┼────────┐      ┌──────┼──────┐       ┌───────┼────────┐
        │       │        │      │      │      │       │       │        │
        ▼       ▼        ▼      ▼      ▼      ▼       ▼       ▼        ▼
      Local    HF     Kaggle  Local  Kaggle  Style  Local   Kaggle   BERT*
       ML    Models   Models    ML    Models  /Heur.  ML     Models  Phish
        │       │        │      │      │      │       │       │        │
        └───────┴────────┘      └──────┴──────┘       └───────┴────────┘
                │                      │                      │
                └──────────────────────┼──────────────────────┘
                                       │
                                       ▼
                         ┌──────────────────────────────┐
                         │       EVIDENCE LAYER         │
                         │                              │
                         │  🏛️ PIB FACT CHECK          │
                         │  🔍 SEARCH COVERAGE TRUST    │
                         │  🌐 URL / DOMAIN TRUST       │
                         │  📰 RELATED ARTICLES         │
                         │  ⏱️ TEMPORAL CURRENTNESS     │
                         │  🔗 SOURCE INDEPENDENCE      │
                         └──────────────┬───────────────┘
                                        │
                       ┌────────────────┴────────────────┐
                       │                                 │
                       ▼                                 ▼
             ┌────────────────────┐           ┌────────────────────┐
             │  🏛️ PIB FACT       │           │  🔍 SEARCH         │
             │     CHECK          │           │     COVERAGE       │
             │                    │           │                    │
             │ • Claim Matching   │           │ • Related Sources  │
             │ • Verdict Match    │           │ • Domain Trust     │
             │ • Relevance Check  │           │ • Source Diversity │
             │ • Confidence       │           │ • Trust Ratio      │
             │ • No Match =       │           │ • No Evidence =    │
             │   NO VOTE          │           │   NO VOTE          │
             └──────────┬─────────┘           └──────────┬─────────┘
                        │                                │
                        └────────────────┬───────────────┘
                                         │
                                         ▼
                         ┌──────────────────────────────┐
                         │     OPTIONAL GEMINI          │
                         │      VERIFICATION            │
                         │                              │
                         │  • Claim Analysis             │
                         │  • Search Grounding            │
                         │  • Source Cross-checking       │
                         │  • Independent Assessment      │
                         │                              │
                         │  If unavailable / 429:         │
                         │  → Offline Python fallback     │
                         └──────────────┬───────────────┘
                                        │
                                        ▼
                         ┌──────────────────────────────┐
                         │     EVIDENCE NORMALIZATION   │
                         │                              │
                         │  • Confidence Normalization  │
                         │  • Voter Validation           │
                         │  • Duplicate Removal          │
                         │  • Source Deduplication      │
                         │  • Invalid Vote Filtering     │
                         │                              │
                         │  REAL / FAKE / NO VOTE       │
                         └──────────────┬───────────────┘
                                        │
                                        ▼
                         ┌──────────────────────────────┐
                         │     WEIGHTED ENSEMBLE        │
                         │       MODEL POLL             │
                         │                              │
                         │  confidence × voter weight   │
                         │                              │
                         │  • Model Agreement           │
                         │  • Evidence Strength          │
                         │  • Voter Reliability          │
                         │  • Weighted Share             │
                         │  • Vote Margin                │
                         │  • Tie Detection              │
                         │  • Unanimous Detection        │
                         └──────────────┬───────────────┘
                                        │
                                        ▼
                         ┌──────────────────────────────┐
                         │     CROSS-EVIDENCE           │
                         │        SYNTHESIS             │
                         │                              │
                         │  • Compare independent       │
                         │    evidence sources          │
                         │  • Resolve conflicting       │
                         │    signals                   │
                         │  • Calculate final confidence│
                         │  • Build explanation          │
                         └──────────────┬───────────────┘
                                        │
                                        ▼
                         ┌──────────────────────────────┐
                         │         FINAL RESULT         │
                         │                              │
                         │  🟢 REAL / 🔴 FAKE / ⚪      │
                         │     INCONCLUSIVE             │
                         │                              │
                         │  • Winner                    │
                         │  • Confidence                │
                         │  • Vote Ratio                │
                         │  • Weighted Share            │
                         │  • Vote Margin               │
                         │  • Tie Flag                  │
                         │  • Per-model Breakdown       │
                         │  • PIB Evidence              │
                         │  • Search Coverage           │
                         │  • Related Sources            │
                         │  • Supporting Evidence        │
                         └──────────────┬───────────────┘
                                        │
                                        ▼
                         ┌──────────────────────────────┐
                         │       REACT RESULT UI        │
                         │                              │
                         │  • Verdict Card              │
                         │  • Confidence Meter          │
                         │  • Model Poll                │
                         │  • Evidence Dashboard        │
                         │  • Source Clusters            │
                         │  • Related Articles          │
                         │  • Live Analysis Timeline    │
                         └──────────────────────────────┘


        * BERTPhish = Optional phishing model
```

---

# 📰 News Analysis

The news pipeline is designed as a multi-stage evidence workflow.

```text
USER CLAIM / ARTICLE
        │
        ▼
CLAIM EXTRACTION
        │
        ├──────────────► TEMPORAL / CURRENTNESS
        │
        ├──────────────► LOCAL ML MODELS
        │
        ├──────────────► HUGGING FACE MODELS
        │
        ├──────────────► KAGGLE / PRETRAINED MODELS
        │
        ├──────────────► PIB FACT CHECK
        │
        ├──────────────► SEARCH COVERAGE TRUST
        │
        ├──────────────► RELATED ARTICLES
        │
        ├──────────────► SOURCE CLUSTERING
        │
        └──────────────► GEMINI VERIFICATION
                              │
                              ▼
                       OFFLINE FALLBACK
                              │
                              ▼
                     EVIDENCE NORMALIZATION
                              │
                              ▼
                       WEIGHTED ENSEMBLE
                              │
                              ▼
                      CROSS-EVIDENCE
                        SYNTHESIS
                              │
                              ▼
                       FINAL VERDICT
```

---

# 🏛️ PIB Fact Check

PIB Fact Check is treated as an **evidence voter**, not as a generic ML model.

The system attempts to identify an official PIB fact-check that is genuinely relevant to the supplied claim.

## PIB workflow

```text
Claim
  │
  ▼
Headline / keyword extraction
  │
  ▼
PIB discovery
  │
  ▼
Candidate fact-checks
  │
  ▼
Content retrieval
  │
  ▼
Claim + verdict matching
  │
  ▼
Relevance validation
  │
  ▼
PIB vote
```

The system should consider:

* Claim similarity
* Important entities
* Distinctive keywords
* Explicit fact-check verdict language
* Page relevance
* Source authenticity

### Important rule

```text
No PIB match
     ↓
NO VOTE
```

It must **not** become:

```text
No PIB match
     ↓
FAKE
```

because PIB does not fact-check every claim.

---

# 🔍 Search Coverage Trust

Search Coverage Trust determines whether independent online coverage supports or contradicts a claim.

```text
Claim
  │
  ▼
Search providers
  │
  ▼
Search results
  │
  ▼
Source extraction
  │
  ▼
Domain classification
  │
  ▼
Source trust evaluation
  │
  ▼
Independent coverage
  │
  ▼
Trust ratio
  │
  ▼
Coverage vote
```

The system can consider:

* Number of usable sources
* Source reputation
* Government sources
* Established news organizations
* Domain characteristics
* Source diversity
* Duplicate sources
* Suspicious domains
* Lookalike domains

### Coverage voting

A simplified model:

```text
Trusted coverage >= 60%
        ↓
      REAL

Trusted coverage <= 35%
        ↓
      FAKE

35% < coverage < 60%
        ↓
     NO VOTE
```

A minimum amount of usable coverage should exist before Search Coverage contributes a vote.

Therefore:

```text
No search results
       ≠
     FAKE
```

This distinction is critical for avoiding false conclusions.

---

# ⭐ Review Analysis

Review analysis uses a combination of:

```text
Review Text
     │
     ├──► Local ML
     │
     ├──► Kaggle / pretrained model
     │
     ├──► Writing-style heuristics
     │
     └──► Ensemble
             │
             ▼
        Final Assessment
```

Potential signals include:

* Repetition
* Extreme sentiment
* Generic language
* Suspicious wording
* Review structure
* Model classification
* Confidence

---

# 🔗 Phishing Detection

The phishing pipeline focuses on URL-level risk.

```text
URL
 │
 ├──► URL Parser
 │
 ├──► Structural Features
 │
 ├──► Domain Analysis
 │
 ├──► Suspicious Pattern Detection
 │
 ├──► Local ML
 │
 ├──► Pretrained Models
 │
 └──► Optional BERTPhish
          │
          ▼
     Weighted Result
```

Potential URL indicators include:

* Excessive subdomains
* IP addresses instead of domains
* Suspicious URL length
* Encoded characters
* Unusual ports
* Typosquatting
* Suspicious TLD patterns
* Login/payment terminology
* Redirect behavior
* Domain trust signals

---

# 🤖 Machine Learning Layer

TrustGuard supports multiple model sources.

## Local Models

Example:

```text
models/
├── news_model.joblib
├── news_vectorizer.joblib
├── review_model.joblib
├── review_vectorizer.joblib
└── local_phishing_model.joblib
```

Typical local approaches include:

* Logistic Regression
* Naive Bayes
* Random Forest
* TF-IDF vectorization

---

## 🤗 Hugging Face

Additional transformer-based models can be enabled for news classification.

Models are loaded independently.

If one model:

* Cannot be downloaded
* Is private
* Has changed
* Is incompatible
* Times out

the remaining pipeline should continue.

---

## 📦 Kaggle / Pretrained Models

TrustGuard can discover compatible pretrained artifacts.

Example files may include:

```text
fake_news_model.pkl
tfidf_vectorizer.pkl

Review_classifier_LG.pkl
scaling_pipeline.pkl
vectorization_pipeline.pkl
```

Models are validated before being used.

An incompatible model should result in:

```text
MODEL_UNAVAILABLE
```

rather than bringing down the complete service.

---

# ✨ Gemini Integration

Gemini is an **optional external verification layer**.

It can be used for:

* Claim verification
* Source analysis
* Search-grounded verification
* Article interpretation
* Translation
* Summarization
* Cross-evidence reasoning

Gemini should not be treated as the only source of truth.

---

## Gemini Failure Handling

If Gemini returns:

```text
429 RESOURCE_EXHAUSTED
```

or becomes unavailable:

```text
Gemini
  │
  ├── available → Gemini verification
  │
  └── unavailable
          │
          ▼
   Offline Python fallback
```

News analysis should continue whenever sufficient non-Gemini evidence exists.

---

# 🔑 Gemini API Keys

Multiple keys may be configured where supported:

```env
GEMINI_API_KEYS=key_one,key_two,key_three
```

When one key reaches its quota, the system can rotate to another available key.

Do not commit API keys to Git.

---

# ⚖️ Weighted Ensemble

TrustGuard does not simply count votes.

Each valid voter contributes based on:

```text
Weighted Score
=
Confidence × Voter Weight
```

The final result considers:

* Number of valid votes
* Confidence
* Voter reliability
* Evidence strength
* Source independence
* Weighted share
* Vote margin
* Tie state

---

## Example

```text
Local ML              → Fake   0.82
Hugging Face          → Fake   0.76
Kaggle                → Real   0.61
PIB Fact Check        → Fake   0.95
Search Coverage       → Fake   0.88
Gemini                → Fake   0.84
```

The ensemble does not treat these as six identical votes.

Evidence-backed voters can receive appropriate weights.

---

# 🧩 Evidence Normalization

Before ensemble voting, TrustGuard normalizes evidence.

```text
Raw Predictions
      │
      ▼
Validate prediction
      │
      ▼
Validate confidence
      │
      ▼
Remove duplicates
      │
      ▼
Normalize labels
      │
      ▼
Filter unavailable voters
      │
      ▼
Calculate voter weights
      │
      ▼
Weighted Ensemble
```

Supported states include:

```text
REAL
FAKE
NO VOTE
UNAVAILABLE
INCONCLUSIVE
```

### Important

`NO VOTE` is different from `FAKE`.

For example:

```text
PIB:
No matching fact-check
→ NO VOTE
```

and:

```text
Search:
Insufficient independent coverage
→ NO VOTE
```

---

# 🔗 Source Independence

Multiple websites repeating the same article does not necessarily mean multiple independent confirmations.

TrustGuard therefore groups sources into clusters where possible.

```text
Source A ─┐
Source B ─┼── Same underlying story
Source C ─┘
     │
     ▼
One evidence cluster
```

This prevents copied articles from artificially inflating evidence.

---

# ⏱️ Temporal Analysis

News can change over time.

TrustGuard can classify whether information appears:

* Current
* Recent
* Historical
* Undated
* Stale
* Time-sensitive

Temporal analysis helps distinguish:

```text
Old true story
```

from:

```text
Current false claim
```

or:

```text
Old article being presented as current
```

---

# 📡 Live SSE Analysis

News analysis supports real-time progress using Server-Sent Events.

Endpoint:

```text
POST /analyze/news/stream
```

The frontend can receive events such as:

```text
analysis_started

claim_extraction_started
claim_extracted

model_started
model_completed
model_unavailable
vote_added

temporal_classified

search_started
search_completed
search_skipped
search_failed

article_found
article_extracted
article_analyzed

source_clustering_started
source_cluster_created

cross_evidence_started
cross_evidence_completed

final_result
analysis_completed
```

---

## SSE Flow

```text
React
  │
  │ POST /analyze/news/stream
  ▼
Node Express
  │
  │ SSE Proxy
  ▼
Python FastAPI
  │
  ├── Claim
  ├── ML
  ├── PIB
  ├── Search
  ├── Articles
  ├── Clustering
  ├── Synthesis
  │
  ▼
final_result
  │
  ▼
analysis_completed
  │
  ▼
React UI
```

The frontend displays:

* Current stage
* Model status
* Live model votes
* Related article count
* Search progress
* Final result

---

# 📁 Project Structure

```text
TrustGuard/
│
├── client/
│   ├── src/
│   │   ├── components/
│   │   │   ├── Navbar.jsx
│   │   │   ├── AuthModal.jsx
│   │   │   ├── TabNavigation.jsx
│   │   │   ├── NewsInput.jsx
│   │   │   ├── ReviewInput.jsx
│   │   │   ├── PhishingInput.jsx
│   │   │   ├── ResultCard.jsx
│   │   │   ├── EvidenceDashboard.jsx
│   │   │   ├── LiveAnalysisProgress.jsx
│   │   │   └── ...
│   │   │
│   │   ├── App.jsx
│   │   └── main.jsx
│   │
│   ├── .env
│   ├── package.json
│   └── vite.config.js
│
├── server/
│   ├── src/
│   │   ├── routes/
│   │   ├── controllers/
│   │   ├── middleware/
│   │   └── index.js
│   │
│   ├── .env
│   └── package.json
│
├── ml-service/
│   ├── models/
│   ├── pretrained_models/
│   ├── main.py
│   ├── requirements.txt
│   └── .env
│
├── .gitignore
└── README.md
```

---

# 🧰 Technology Stack

## Frontend

```text
React
Vite
Bootstrap
CSS
Server-Sent Events
```

## API Gateway

```text
Node.js
Express
REST API
SSE Proxy
```

## ML Service

```text
Python
FastAPI
Uvicorn
scikit-learn
Joblib
PyTorch
Transformers
```

## Verification

```text
PIB Fact Check
Search Coverage
BeautifulSoup
HTTP clients
Gemini API
Search providers
```

---

# ⚙️ Installation

## Prerequisites

Install:

* Node.js
* npm
* Python 3.x
* pip
* Git

Optional:

* CUDA-enabled PyTorch
* Gemini API key
* Hugging Face access
* Kaggle access

---

# 1. Clone Repository

```bash
git clone <repository-url>
cd TrustGuard
```

---

# 2. Install Python Dependencies

```bash
cd ml-service
python -m pip install -r requirements.txt
```

---

# 3. Install Node Dependencies

From the server:

```bash
cd ../server
npm install
```

From the frontend:

```bash
cd ../client
npm install
```

---

# 🔧 Environment Configuration

## Python `.env`

Create:

```text
ml-service/.env
```

Example:

```env
HOST=127.0.0.1
PORT=8000

MODELS_DIR=models
PRETRAINED_MODELS_DIR=pretrained_models

GEMINI_API_KEYS=key_one,key_two
GEMINI_MODEL=gemini-3.6-flash

CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173

REQUEST_TIMEOUT=15
MAX_ARTICLE_CHARS=30000
MAX_INPUT_CHARS=100000

LOG_LEVEL=INFO

ENABLE_BERTPHISH=false
ENABLE_HF_NEWS_MODELS=true

HF_NEWS_MODELS=model_one,model_two

ENABLE_DOMAIN_AGE_LOOKUP=false
ENABLE_WEB_SEARCH_VERIFICATION=false

MAX_SEARCH_ARTICLES_TO_FETCH=6
SEARCH_FETCH_WORKERS=4
```

Use the exact variable names supported by the current backend implementation.

---

# 🌐 Frontend `.env`

Create:

```text
client/.env
```

Example:

```env
VITE_API_URL=http://localhost:5000/api/v1
VITE_REQUEST_TIMEOUT=120000
VITE_GEMINI_CONNECT_URL=https://aistudio.google.com/apikey
```

---

# ▶️ Running the Application

TrustGuard is easiest to run using three terminals.

---

## Terminal 1 — Python ML Service

```bash
cd ml-service
python main.py
```

Expected:

```text
http://127.0.0.1:8000
```

---

## Terminal 2 — Node.js Gateway

```bash
cd server
npm run dev
```

or:

```bash
npm start
```

Expected:

```text
http://localhost:5000
```

---

## Terminal 3 — React Frontend

```bash
cd client
npm run dev
```

Expected:

```text
http://localhost:5173
```

Open:

```text
http://localhost:5173
```

---

# 🔌 API Reference

| Method | Endpoint                  | Purpose               |
| ------ | ------------------------- | --------------------- |
| `GET`  | `/health`                 | Service health        |
| `GET`  | `/models/status`          | Model status          |
| `GET`  | `/models/registry`        | Model registry        |
| `GET`  | `/gemini/status`          | Gemini status         |
| `GET`  | `/cache/stats`            | Cache statistics      |
| `POST` | `/analyze/news`           | News analysis         |
| `POST` | `/analyze/news/stream`    | Live news analysis    |
| `POST` | `/analyze/review`         | Review analysis       |
| `POST` | `/analyze/review/page`    | Product page analysis |
| `POST` | `/analyze/phishing`       | Phishing analysis     |
| `POST` | `/analyze/claim`          | Claim extraction      |
| `POST` | `/analyze/temporal`       | Temporal analysis     |
| `POST` | `/analyze/cluster`        | Source clustering     |
| `POST` | `/analyze/news/translate` | Translation           |
| `POST` | `/analyze/news/summary`   | Summarization         |

---

# 📰 News Request

```http
POST /analyze/news
Content-Type: application/json
```

Example:

```json
{
  "headline": "Example news headline",
  "article_url": "https://example.com/news",
  "article_text": "Article content..."
}
```

At least one meaningful input should be provided:

```text
headline
article_url
article_text
```

---

# ⚡ Live News Request

```http
POST /analyze/news/stream
```

Example:

```javascript
const response = await fetch(
  `${API_BASE_URL}/analyze/news/stream`,
  {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Accept": "text/event-stream"
    },
    body: JSON.stringify({
      headline: "Example headline",
      article_url: "https://example.com/news"
    })
  }
);
```

---

# ⭐ Review Request

```http
POST /analyze/review
```

```json
{
  "text": "The product was excellent and arrived on time."
}
```

---

# 🔗 Phishing Request

```http
POST /analyze/phishing
```

```json
{
  "url": "https://example.com/login"
}
```

---

# ❤️ Health & Diagnostics

## Health

```http
GET /health
```

Use this to verify that the Python service is alive.

---

## Models

```http
GET /models/status
```

Useful for identifying:

* Loaded models
* Failed models
* Unavailable models
* Active voters
* Model loading errors

---

## Registry

```http
GET /models/registry
```

Shows registered model adapters.

---

## Gemini

```http
GET /gemini/status
```

Useful for checking:

* Configured keys
* Active key
* Cooldowns
* Quota-related failures

---

## Cache

```http
GET /cache/stats
```

Shows relevant cache information.

---

# 🛡️ Reliability & Fallbacks

TrustGuard is designed to continue operating when optional components fail.

```text
                 ┌───────────────┐
                 │  News Claim   │
                 └───────┬───────┘
                         │
        ┌────────────────┼────────────────┐
        ▼                ▼                ▼
       ML               PIB             Search
        │                │                │
        │             unavailable       failed
        │                │                │
        ▼                ▼                ▼
    Continue          NO VOTE          NO VOTE
        │
        ▼
     Ensemble
```

Gemini:

```text
Gemini available
      │
      ▼
Gemini verification

Gemini unavailable
      │
      ▼
Offline fallback
```

One failed model should not stop the complete analysis.

---

# 🚫 Failure Semantics

TrustGuard distinguishes between:

```text
FAKE
REAL
NO VOTE
UNAVAILABLE
INCONCLUSIVE
```

Examples:

### PIB

```text
No relevant PIB fact-check
→ NO VOTE
```

### Search

```text
Too few independent sources
→ NO VOTE
```

### ML

```text
Model failed to load
→ UNAVAILABLE
```

### Conflicting evidence

```text
No clear winner
→ INCONCLUSIVE / TIE
```

This is preferable to forcing every subsystem to produce a binary answer.

---

# 🔐 Security

## API Keys

Never commit:

```text
.env
```

or API keys to Git.

Use:

```text
.gitignore
```

to protect secrets.

---

## Gemini Keys

Do not:

* Hard-code Gemini keys in React
* Log Gemini keys
* Commit Gemini keys
* Return server-side keys to clients

---

## CORS

Restrict:

```env
CORS_ORIGINS
```

to trusted frontend origins.

---

## SSRF Protection

Because TrustGuard can fetch user-supplied URLs, production deployments should protect against:

* localhost access
* loopback addresses
* private IP ranges
* link-local addresses
* internal hostnames
* cloud metadata endpoints
* malicious redirects

---

## Input Limits

Large requests should be limited using:

```env
MAX_ARTICLE_CHARS
MAX_INPUT_CHARS
```

This helps protect the service from oversized payloads.

---

## Rate Limiting

Production deployments should apply rate limits to:

```text
/analyze/*
```

especially:

```text
/analyze/news
/analyze/news/stream
/analyze/phishing
```

---

# 🧪 Troubleshooting

## `Cannot GET /api/v1/analyze/news`

News analysis requires:

```text
POST
```

not:

```text
GET
```

Opening the endpoint directly in a browser performs a GET request.

---

## `News analysis timed out`

Check:

1. Python service is running.
2. Node gateway is running.
3. Search providers are responding.
4. PIB requests are not blocking the pipeline.
5. Gemini is not being retried indefinitely.
6. Search/article fetches have reasonable timeouts.
7. The SSE connection is not being buffered by a proxy.

Optional external services should fail independently.

---

## Gemini `429 RESOURCE_EXHAUSTED`

This means the Gemini quota has been exhausted or rate-limited.

TrustGuard should:

```text
429
 ↓
Rotate key if available
 ↓
Otherwise use offline fallback
```

Do not continuously retry the same exhausted key.

---

## PIB takes too long

PIB verification should use:

* Request timeouts
* Limited candidate pages
* Caching
* Deduplication
* Independent failure handling

A slow PIB lookup should not block the entire analysis indefinitely.

---

## Search Coverage takes too long

Search should use:

* Multiple providers
* Per-provider timeouts
* Limited result counts
* Limited article fetches
* Concurrent fetching
* Deduplication

If search cannot obtain enough evidence:

```text
SEARCH → NO VOTE
```

rather than:

```text
SEARCH → FAKE
```

---

## Live Analysis Does Not Update

Check:

```text
POST /analyze/news/stream
```

and verify that the response is:

```text
Content-Type: text/event-stream
```

Also ensure the Node gateway is not buffering the stream.

The stream should remain active until:

```text
final_result
analysis_completed
```

---

## Multiple `/analyze/news/stream` Requests

If the terminal shows multiple requests for a single submission:

```text
POST /analyze/news/stream
POST /analyze/news/stream
POST /analyze/news/stream
```

check:

* React effect dependencies
* Duplicate component mounting
* React Strict Mode behavior
* Parent state changes
* Re-created payload objects
* Multiple submit handlers

Only one live analysis request should normally be created per user submission.

---

# 🧑‍💻 Development Workflow

Recommended startup order:

```text
Terminal 1
Python
  ↓
Terminal 2
Node
  ↓
Terminal 3
React
```

Then test:

```text
GET /health
        ↓
GET /models/status
        ↓
News analysis
        ↓
Live SSE
        ↓
Final result
```

---

# 📊 Example Final Result

A final result can contain information such as:

```json
{
  "winner": "Fake",
  "confidence": 84.6,
  "voteRatioConfidence": 80.0,
  "margin": 3,
  "isTie": false,
  "isUnanimous": false,
  "votes": {
    "Fake": 4,
    "Real": 1
  },
  "weightedVotes": {
    "Fake": 3.42,
    "Real": 0.71
  },
  "models": [],
  "evidence": [],
  "sources": []
}
```

The exact response schema may evolve with the backend implementation.

---

# 🗺️ Roadmap

## Verification

* [ ] More government fact-check sources
* [ ] Improved claim matching
* [ ] Better source independence detection
* [ ] More search providers
* [ ] Improved temporal reasoning

## Machine Learning

* [ ] Automated model benchmarking
* [ ] Precision / recall / F1 dashboard
* [ ] Learned voter weights
* [ ] Model drift detection
* [ ] Automatic model health monitoring

## Infrastructure

* [ ] Docker deployment
* [ ] Redis/shared cache
* [ ] Production database
* [ ] Background workers
* [ ] Centralized logging
* [ ] Observability dashboard

## Security

* [ ] Backend authentication
* [ ] Role-based authorization
* [ ] Production rate limiting
* [ ] Advanced SSRF protection
* [ ] Secret management
* [ ] HTTPS deployment

## User Experience

* [ ] Analysis history
* [ ] Evidence timeline
* [ ] Advanced source explorer
* [ ] Exportable verification reports
* [ ] Model comparison dashboard
* [ ] Improved accessibility

---

# 🧠 Design Philosophy

TrustGuard follows five core principles.

### 1. No single model is the truth

A model prediction is evidence, not absolute truth.

### 2. Evidence quality matters

A strong government fact-check can carry more significance than several generic classifier predictions.

### 3. Missing evidence is not false evidence

```text
No PIB result
      ≠
Fake

No search coverage
      ≠
Fake
```

### 4. Independent sources matter

Ten websites copying one article should not automatically count as ten independent confirmations.

### 5. Failure should degrade gracefully

```text
One model fails
     ↓
Other models continue

Gemini fails
     ↓
Offline fallback

PIB unavailable
     ↓
PIB NO VOTE

Search unavailable
     ↓
Search NO VOTE
```

---

# ⚠️ Disclaimer

TrustGuard is an **assistance and risk-assessment system**.

It does not guarantee factual correctness, authenticity, or malicious intent.

A result such as:

```text
REAL
```

does not prove that every statement in an article is true.

Likewise:

```text
FAKE
```

does not automatically prove that every part of a story is false.

A phishing classification indicates potential security risk and should be independently investigated before taking security-sensitive actions.

Users should consider:

* Original sources
* Official announcements
* Government fact-checks
* Reputable journalism
* Publication dates
* Independent evidence
* Context

before making important decisions.

---

# 📄 License

Add the project's selected license here before publishing.

Example:

```text
MIT License
```

if the project is released under MIT.

---

# 👨‍💻 Project

**TrustGuard**

> **Multi-signal verification for a more trustworthy digital world.**

```text
React
  ↓
Node.js / Express
  ↓
Python / FastAPI
  ↓
ML + Evidence + Verification
  ↓
Weighted Ensemble
  ↓
Cross-Evidence Synthesis
  ↓
Explainable Final Result
```

---

## ⭐ Core Concept

```text
                 TRUSTGUARD
                     │
          ┌──────────┼──────────┐
          │          │          │
         NEWS       REVIEW    PHISHING
          │          │          │
          └──────────┼──────────┘
                     │
             MULTI-MODEL LAYER
                     │
                     ▼
              EVIDENCE LAYER
                     │
       ┌─────────────┼─────────────┐
       │             │             │
      PIB          SEARCH        GEMINI
   FACT CHECK     COVERAGE      OPTIONAL
       │             │             │
       └─────────────┼─────────────┘
                     │
                     ▼
             EVIDENCE NORMALIZATION
                     │
                     ▼
              WEIGHTED ENSEMBLE
                     │
                     ▼
             CROSS-EVIDENCE
                SYNTHESIS
                     │
                     ▼
              FINAL VERDICT
                     │
                     ▼
             EXPLAINABLE UI
```

**TrustGuard does not ask "Which model should I trust?"**

It asks:

> **"What evidence is available, how independent is it, how strong is it, and how much do the different signals agree?"**
