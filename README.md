# 🛡️ TrustGuard

TrustGuard is a digital-intelligence and content-verification platform that combines machine-learning models, ensemble voting, Gemini-assisted verification, and web evidence to analyze:

- 📰 Fake news
- ⭐ Fake reviews
- 🔗 Phishing URLs

The project is designed as a full-stack application with a React frontend, Node.js API gateway, and Python/FastAPI ML inference service.

---

## ✨ Features

### 📰 News Verification

TrustGuard can analyze news using:

- Headline only
- Article URL
- Article text
- Headline + URL
- Headline + article text
- URL + article text
- All available inputs together

The news pipeline can combine:

1. Local TF-IDF + Logistic Regression model
2. Kaggle fake-news model
3. Gemini verification
4. Google Search grounding/evidence
5. Related news/source discovery
6. Translation and summarization support
7. Ensemble polling

The final result is selected from the models that actually return a valid prediction.

---

### ⭐ Fake Review Detection

The review module supports:

- Local review classifier
- Local TF-IDF vectorizer
- Kaggle fake-review model
- Vectorization pipeline
- Scaling pipeline
- Ensemble voting

The system reports:

- Genuine/Fake classification
- Confidence
- Spam score
- Readability information
- Individual model predictions
- Final poll winner

---

### 🔗 Phishing URL Detection

The phishing module analyzes URLs using URL-based security features.

Supported model types include:

- Local Random Forest model
- Kaggle Random Forest phishing model
- Optional BERTPhish/Transformers model

The system can inspect:

- HTTPS usage
- URL length
- Domain structure
- Suspicious keywords
- Special characters
- TLD characteristics
- Host/domain properties
- Model-specific feature sets

The system does **not** assume that models with different feature counts use the same feature order. Model-specific adapters are used where required.

---

# 🏗️ Architecture

```text
                         ┌─────────────────────┐
                         │    React Frontend   │
                         │       Vite          │
                         └──────────┬──────────┘
                                    │
                                    ▼
                         ┌─────────────────────┐
                         │  Node.js API        │
                         │  Express Gateway    │
                         └──────────┬──────────┘
                                    │
                                    ▼
                         ┌─────────────────────┐
                         │ Python ML Service   │
                         │ FastAPI / Uvicorn   │
                         └──────────┬──────────┘
                                    │
              ┌─────────────────────┼─────────────────────┐
              │                     │                     │
              ▼                     ▼                     ▼
          📰 NEWS                ⭐ REVIEW            🔗 PHISHING
              │                     │                     │
       ┌──────┼──────┐       ┌──────┼──────┐       ┌──────┼──────┐
       │      │      │       │      │      │       │      │      │
     Local  Kaggle Gemini   Local  Kaggle  ...   Local  Kaggle BERT*
       │      │      │       │      │              │      │
       └──────┴──────┘       └──────┴──────┘       └──────┴──────┘
              │                     │                     │
              └─────────────────────┼─────────────────────┘
                                    ▼
                            ┌─────────────────┐
                            │  MODEL POLL     │
                            │  / ENSEMBLE     │
                            └────────┬────────┘
                                     │
                                     ▼
                              FINAL RESULT
```

`* BERTPhish is optional and depends on a compatible PyTorch, torchvision, and Transformers environment.`

---

# 📁 Project Structure

Recommended structure:

```text
Trust-Guard/
│
├── TrustGuard/
│   │
│   ├── ml-service/
│   │   ├── main.py
│   │   ├── .env
│   │   ├── requirements.txt
│   │   │
│   │   ├── models/
│   │   │   ├── news_model.joblib
│   │   │   ├── news_vectorizer.joblib
│   │   │   ├── review_model.joblib
│   │   │   ├── review_vectorizer.joblib
│   │   │   └── local_phishing_model.joblib
│   │   │
│   │   └── pretrained_models/
│   │       └── model_paths.json
│   │
│   ├── server/
│   │   ├── routes/
│   │   ├── controllers/
│   │   └── ...
│   │
│   └── frontend/
│       ├── src/
│       ├── public/
│       ├── package.json
│       └── ...
│
├── .gitignore
└── README.md
```

Your exact frontend/backend folder names may differ; the important requirement is that the Python service can locate its `models/` directory.

---

# 🤖 Models

## Local Models

The current local ML service supports:

| Module | Model | Vectorizer/Features |
|---|---|---|
| News | Logistic Regression | TF-IDF |
| Review | Multinomial Naive Bayes | TF-IDF |
| Phishing | Random Forest | URL features |

The local models are loaded from:

```text
ml-service/models/
```

Expected files:

```text
news_model.joblib
news_vectorizer.joblib

review_model.joblib
review_vectorizer.joblib

local_phishing_model.joblib
```

---

## Kaggle Models

The project can integrate downloaded Kaggle models through `kagglehub`.

Current model sources used by the project include:

```text
thedeveloper306/fake-review-detector-model
saitejabandaruin/truthlens
angelchaudhary/fake-news-detection-model
lucasrobson/bertphish
christinecoomans/phishing_detection_random_forest_v1
```

Kaggle model downloads generally return a **directory**, not a single `.joblib` file.

Therefore the loader searches the downloaded directory and handles different model formats separately.

### Fake News

Expected bundle:

```text
fake_news_model.pkl
tfidf_vectorizer.pkl
```

Both files must be used together.

### Fake Reviews

Expected bundle:

```text
Review_classifier_LG.pkl
scaling_pipeline.pkl
vectorization_pipeline.pkl
```

These are treated as a single model pipeline.

### Phishing

The Kaggle phishing model may require a different feature count from the local model.

For example:

```text
Local model  → 13 features
Kaggle model → 21 features
```

The system must not feed the 13-feature representation into the 21-feature model.

### BERTPhish

BERTPhish is a Transformers/PyTorch model and is loaded separately from Joblib models.

---

# 🗳️ Ensemble / Model Poll

TrustGuard does not simply average every configured model.

A model participates in the poll **only when it successfully produces a valid prediction**.

Example:

```text
MODEL POLL

✓ Local News Model          REAL      91.4%
✓ Kaggle Fake News Model    FAKE      84.7%
✓ Gemini + Search           REAL

──────────────────────────────

REAL     2 votes
FAKE     1 vote

🏆 FINAL RESULT: REAL
```

If a model fails:

```text
⚠ BERTPhish
  Not available
```

it is not counted as a vote.

This prevents a failed or incompatible model from artificially influencing the result.

---

# 🧠 Gemini Integration

Gemini is used as an additional verification/evidence layer, particularly for news.

Possible functions include:

- Claim analysis
- News verification
- Related news
- Search-grounded evidence
- Article summarization
- Translation
- Source comparison

Google Search grounding can be used to provide current web evidence to the Gemini analysis.

## API Key

Create a Gemini API key using Google AI Studio.

Do **not** put the key in the React frontend.

Recommended:

```text
React
  ↓
Node.js
  ↓
Python
  ↓
Gemini
```

The Python service can use a server-side key:

```env
GEMINI_API_KEY=YOUR_KEY
```

It can also support a client-provided key when your authentication/backend design explicitly permits it.

### Security

Never:

```text
❌ commit .env
❌ put GEMINI_API_KEY in React source
❌ put API keys in URLs
❌ expose API keys in GitHub
```

Add to `.gitignore`:

```gitignore
.env
*.env
```

---

# ⚙️ Environment Configuration

Create:

```text
ml-service/.env
```

Example:

```env
MODELS_DIR=models
PRETRAINED_MODELS_DIR=pretrained_models

HOST=127.0.0.1
PORT=8000
RELOAD=true

GEMINI_API_KEY=YOUR_GEMINI_API_KEY
GEMINI_MODEL=gemini-3.6-flash

CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173

REQUEST_TIMEOUT=15
MAX_ARTICLE_CHARS=30000
LOG_LEVEL=INFO

ENABLE_BERTPHISH=false
```

### Important

Use:

```env
MODELS_DIR=models
PRETRAINED_MODELS_DIR=pretrained_models
```

rather than hard-coded Windows paths.

The service resolves these relative to the `ml-service` directory.

---

# 🐍 Python ML Service Setup

## 1. Open the ML directory

Windows PowerShell:

```powershell
cd "C:\Git PC\Trust-Guard\TrustGuard\ml-service"
```

## 2. Install dependencies

```powershell
python -m pip install -r requirements.txt
```

If `requirements.txt` is not available:

```powershell
python -m pip install fastapi uvicorn python-dotenv joblib pandas numpy scikit-learn requests beautifulsoup4 google-genai
```

Optional Transformers support:

```powershell
python -m pip install transformers accelerate safetensors
```

---

# ▶️ Start the ML Service

Run:

```powershell
python main.py
```

Expected:

```text
Uvicorn running on http://127.0.0.1:8000
Application startup complete.
```

The service should report model status similar to:

```text
Models ready |
news=True |
review=True |
phishing=True |
pretrained=3 |
bertphish=False
```

---

# ❤️ Health Check

Open:

```text
http://127.0.0.1:8000/health
```

Expected:

```json
{
  "status": "UP"
}
```

---

# 🔍 Model Status

Open:

```text
http://127.0.0.1:8000/models/status
```

This endpoint should be used to verify which models are actually available.

Example:

```json
{
  "news": true,
  "review": true,
  "phishing": true,
  "pretrained": 3,
  "bertphish": false
}
```

---

# 🔌 API Endpoints

## Health

```http
GET /health
```

## Model Status

```http
GET /models/status
```

## News

```http
POST /analyze/news
```

Example:

```json
{
  "headline": "Example headline",
  "article_url": "https://example.com/news",
  "article_text": "Article content..."
}
```

At least one meaningful news input should be supplied.

---

## Review

```http
POST /analyze/review
```

Payload:

```json
{
  "text": "The product was excellent and arrived on time."
}
```

---

## Phishing

```http
POST /analyze/phishing
```

Payload:

```json
{
  "url": "https://example.com/login"
}
```

---

# 🔗 Node.js API Gateway

The Node.js server acts as the public API gateway.

Typical flow:

```text
React
  ↓
http://localhost:5000/api/v1/...
  ↓
Node.js Express
  ↓
http://127.0.0.1:8000
  ↓
Python ML Service
```

Example environment variable:

```env
PYTHON_ML_SERVICE_URL=http://127.0.0.1:8000
```

Start the Node server using your project's package scripts, commonly:

```powershell
npm install
npm run dev
```

or:

```powershell
npm start
```

Check your `package.json` for the exact script.

---

# ⚛️ React Frontend

The frontend communicates with the Node API rather than directly exposing ML internals.

Typical frontend environment:

```env
VITE_API_URL=http://localhost:5000/api/v1
```

Run:

```powershell
npm install
npm run dev
```

The Vite development server is normally:

```text
http://localhost:5173
```

---

# 🔄 News Verification Flow

```text
User enters:

Headline
   +
URL
   +
Article text
       │
       ▼
Normalize input
       │
       ├── URL extraction
       ├── Article extraction
       └── Text cleaning
       │
       ▼
Local ML
       │
       ▼
Kaggle ML
       │
       ▼
Gemini + Search
       │
       ▼
Evidence / Related Sources
       │
       ▼
Model Poll
       │
       ▼
Final Result
```

---

# 🧪 Troubleshooting

## `Cannot GET /api/v1/analyze/news`

The endpoint is a `POST`, not a `GET`.

Correct:

```http
POST /api/v1/analyze/news
```

Opening it directly in a browser sends `GET`, which results in:

```text
Cannot GET /api/v1/analyze/news
```

---

## `Unexpected token '<'`

This usually means the frontend expected JSON but received an HTML page.

Typical causes:

- Wrong API port
- Wrong API URL
- Node route not registered
- Python service URL incorrectly configured
- Vite/frontend server returning HTML

Check:

```text
React → Node → Python
```

and verify each service independently.

---

## Models show `False`

Check:

```text
http://127.0.0.1:8000/models/status
```

Then inspect startup diagnostics.

Make sure:

```text
ml-service/
└── models/
```

contains the expected `.joblib` files.

---

## `pretrained=0`

This does not necessarily mean KaggleHub failed.

KaggleHub model downloads commonly return directories.

The service must discover the actual model files inside those directories and load them according to their format.

---

## BERTPhish fails

BERTPhish requires a compatible:

```text
PyTorch
+
torchvision
+
Transformers
```

environment.

A common error is:

```text
RuntimeError:
operator torchvision::nms does not exist
```

This indicates an incompatible PyTorch/torchvision installation.

BERTPhish is intentionally optional so that the rest of TrustGuard continues working.

---

# 🧩 Recommended BERTPhish Environment

For stability, consider running BERTPhish in a separate environment rather than changing the environment that already runs the sklearn models.

Example:

```powershell
conda create -n trustguard-bert python=3.11 -y
conda activate trustguard-bert
```

Then install a compatible PyTorch/torchvision pair and Transformers.

Test:

```powershell
python -c "import torch; print(torch.__version__)"
```

```powershell
python -c "import torchvision; print(torchvision.__version__)"
```

```powershell
python -c "from transformers import BertForSequenceClassification; print('BERT OK')"
```

Only enable BERTPhish after those imports work.

---

# 📊 Current Model Strategy

TrustGuard intentionally distinguishes between:

### Participating

```text
Model successfully loaded
+
Model successfully predicted
```

### Skipped

```text
Model unavailable
OR
Model incompatible
OR
Required feature pipeline unavailable
OR
Prediction failed
```

A skipped model must **not** receive a vote.

This keeps the final ensemble result honest.

---

# 🔐 Security Notes

Before deploying publicly:

- Use authentication.
- Restrict CORS.
- Never expose server Gemini keys.
- Rate-limit analysis endpoints.
- Validate URLs before fetching.
- Set request timeouts.
- Limit article size.
- Avoid SSRF when fetching arbitrary URLs.
- Do not blindly trust extracted article content.
- Store user-provided API keys securely if user-key support is implemented.
- Do not commit `.env`.
- Do not log API keys.
- Do not expose internal model paths in production responses.

---

# 🚀 Production Roadmap

Recommended future improvements:

- [ ] User authentication
- [ ] User-owned Gemini API keys
- [ ] Encrypted API-key storage
- [ ] Redis/cache for repeated URLs
- [ ] Rate limiting
- [ ] Background article extraction
- [ ] Database for analysis history
- [ ] Model performance dashboard
- [ ] Precision/recall/F1 tracking
- [ ] Per-model reliability weights
- [ ] Human feedback on predictions
- [ ] BERTPhish isolated inference worker
- [ ] Automatic model health monitoring
- [ ] Docker deployment
- [ ] HTTPS
- [ ] Production logging/monitoring

---

# ⚠️ Important ML Disclaimer

TrustGuard provides **risk assessment and model-based analysis**, not absolute truth.

A model prediction such as:

```text
REAL
```

does not prove that an article is true.

Likewise:

```text
PHISHING
```

is a security-risk classification and should be investigated using additional evidence.

For news verification, the strongest result should combine:

```text
ML prediction
+
independent sources
+
current web evidence
+
Gemini analysis
```

rather than relying on one classifier.

---

# 📜 License

Add the project's intended license here before publishing the repository.

---

# 👨‍💻 Development

TrustGuard is built around:

```text
React
Node.js
Express
Python
FastAPI
scikit-learn
Joblib
KaggleHub
Google Gemini
Transformers
PyTorch
```

The system is designed to remain functional even when optional models such as BERTPhish are unavailable.
