# ============================================================
# TRUST GUARD
# ============================================================
#
# Features
# ------------------------------------------------------------
# 1. Fake News Detection
#       - Headline
#       - Article URL
#       - Headline + URL
#       - Local ML model
#       - Kaggle pretrained model(s)
#       - Gemini + Google Search
#       - Gemini URL Context
#       - Related news
#       - Source citations
#       - Translation
#       - Summary
#       - FINAL MAJORITY POLL
#
# 2. Fake Review Detection
#       - Local Kaggle-trained model
#       - Pretrained Kaggle models
#       - FINAL MAJORITY POLL
#
# 3. Phishing URL Detection
#       - Local URL Random Forest
#       - Kaggle Random Forest
#       - BERTPhish
#       - FINAL MAJORITY POLL
#
# 4. Cybersecurity Dataset
#       - Download
#       - Clean
#       - Save
#
# ============================================================

import os
import re
import glob
import json
import warnings
import joblib
import requests
import kagglehub
import numpy as np
import pandas as pd

from collections import Counter
from urllib.parse import urlparse

from sklearn.model_selection import train_test_split
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.naive_bayes import MultinomialNB
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    accuracy_score,
    precision_score,
    recall_score,
    f1_score,
    classification_report,
    confusion_matrix
)

warnings.filterwarnings("ignore")


# ============================================================
# CONFIGURATION
# ============================================================

BASE_DIR = os.path.dirname(
    os.path.abspath(__file__)
)

DATA_DIR = os.path.join(
    BASE_DIR,
    "data"
)

CLEAN_DIR = os.path.join(
    BASE_DIR,
    "cleaned_data"
)

MODELS_DIR = os.path.join(
    BASE_DIR,
    "models"
)

PRETRAINED_DIR = os.path.join(
    BASE_DIR,
    "pretrained_models"
)

RESULTS_DIR = os.path.join(
    BASE_DIR,
    "results"
)

for folder in [
    DATA_DIR,
    CLEAN_DIR,
    MODELS_DIR,
    PRETRAINED_DIR,
    RESULTS_DIR
]:
    os.makedirs(
        folder,
        exist_ok=True
    )


# ============================================================
# KAGGLE DATASETS
# ============================================================

NEWS_DATASET = (
    "mobeenfatimah/"
    "fake-news-detection-dataset-6000-news-articles"
)

REVIEW_DATASET = (
    "mexwell/"
    "fake-reviews-dataset"
)

CYBER_DATASET = (
    "atharvasoundankar/"
    "global-cybersecurity-threats-2015-2024"
)


# ============================================================
# KAGGLE PRETRAINED MODELS
# ============================================================

PRETRAINED_MODELS = {

    "fake_review_model":
        "thedeveloper306/"
        "fake-review-detector-model/"
        "scikitLearn/default",

    "truthlens":
        "saitejabandaruin/"
        "truthlens/"
        "pyTorch/pytorch",

    "fake_news_model":
        "angelchaudhary/"
        "fake-news-detection-model/"
        "scikitLearn/default",

    "bertphish":
        "lucasrobson/"
        "bertphish/"
        "transformers/default",

    "phishing_random_forest":
        "christinecoomans/"
        "phishing_detection_random_forest_v1/"
        "scikitLearn/default"
}


# ============================================================
# GENERAL TEXT CLEANING
# ============================================================

def clean_text(text):

    if text is None:
        return ""

    if pd.isna(text):
        return ""

    text = str(text)

    text = re.sub(
        r"http\S+|www\S+",
        " ",
        text
    )

    text = re.sub(
        r"<.*?>",
        " ",
        text
    )

    text = re.sub(
        r"\S+@\S+\.\S+",
        " ",
        text
    )

    text = re.sub(
        r"[^a-zA-Z0-9\s]",
        " ",
        text
    )

    text = re.sub(
        r"\s+",
        " ",
        text
    )

    return text.strip().lower()


# ============================================================
# DATAFRAME CLEANING
# ============================================================

def clean_dataframe(df):

    df = df.copy()

    df.columns = (
        df.columns
        .astype(str)
        .str.strip()
        .str.lower()
        .str.replace(
            " ",
            "_"
        )
        .str.replace(
            r"[^\w]",
            "",
            regex=True
        )
    )

    df = df.dropna(
        axis=1,
        how="all"
    )

    df = df.dropna(
        axis=0,
        how="all"
    )

    df = df.drop_duplicates()

    for col in df.select_dtypes(
        include="object"
    ).columns:

        df[col] = (
            df[col]
            .astype(str)
            .str.strip()
        )

    return df.reset_index(
        drop=True
    )


# ============================================================
# CSV DISCOVERY
# ============================================================

def find_csv_files(folder):

    return glob.glob(
        os.path.join(
            folder,
            "**",
            "*.csv"
        ),
        recursive=True
    )


def load_first_csv(
    folder,
    dataset_name
):

    files = find_csv_files(
        folder
    )

    print("\n" + "=" * 70)
    print(dataset_name)
    print("=" * 70)

    if not files:

        raise FileNotFoundError(
            f"No CSV files found in {folder}"
        )

    for file in files:

        print(
            "Found:",
            file
        )

    for file in files:

        try:

            df = pd.read_csv(
                file,
                low_memory=False
            )

            if len(df) > 0:

                print(
                    "\nLoaded:",
                    file
                )

                print(
                    "Shape:",
                    df.shape
                )

                print(
                    "Columns:",
                    list(df.columns)
                )

                return df

        except Exception as e:

            print(
                "Could not read:",
                file,
                e
            )

    raise ValueError(
        f"Unable to load {dataset_name}"
    )


# ============================================================
# COLUMN DETECTION
# ============================================================

def find_column(
    df,
    candidates
):

    for candidate in candidates:

        if candidate in df.columns:

            return candidate

    return None


# ============================================================
# DOWNLOAD DATASETS
# ============================================================

def download_datasets():

    print("\n")
    print("=" * 70)
    print("DOWNLOADING KAGGLE DATASETS")
    print("=" * 70)

    paths = {}

    paths["news"] = (
        kagglehub.dataset_download(
            NEWS_DATASET
        )
    )

    paths["reviews"] = (
        kagglehub.dataset_download(
            REVIEW_DATASET
        )
    )

    paths["cyber"] = (
        kagglehub.dataset_download(
            CYBER_DATASET
        )
    )

    for name, path in paths.items():

        print(
            f"{name}: {path}"
        )

    return paths


# ============================================================
# TRAIN NEWS MODEL
# ============================================================

def train_news_model(
    news_path
):

    df = load_first_csv(
        news_path,
        "FAKE NEWS DATASET"
    )

    df = clean_dataframe(
        df
    )

    text_column = find_column(
        df,
        [
            "text",
            "article",
            "article_text",
            "news",
            "content",
            "body",
            "title"
        ]
    )

    label_column = find_column(
        df,
        [
            "label",
            "class",
            "target",
            "category",
            "fake",
            "is_fake"
        ]
    )

    print(
        "\nDetected text column:",
        text_column
    )

    print(
        "Detected label column:",
        label_column
    )

    if (
        text_column is None
        or label_column is None
    ):

        print(
            "\nCould not detect news columns."
        )

        print(
            "Available:",
            list(df.columns)
        )

        return None

    df = df.dropna(
        subset=[
            text_column,
            label_column
        ]
    )

    df["clean_text"] = (
        df[text_column]
        .apply(clean_text)
    )

    df = df[
        df["clean_text"].str.len() > 10
    ]

    df = df.drop_duplicates(
        subset=["clean_text"]
    )

    clean_file = os.path.join(
        CLEAN_DIR,
        "cleaned_news.csv"
    )

    df.to_csv(
        clean_file,
        index=False
    )

    print(
        "\nCleaned news dataset:",
        df.shape
    )

    X = df["clean_text"]
    y = df[label_column]

    print(
        "\nClass distribution:"
    )

    print(
        y.value_counts()
    )

    X_train, X_test, y_train, y_test = (
        train_test_split(
            X,
            y,
            test_size=0.20,
            random_state=42,
            stratify=y
        )
    )

    vectorizer = TfidfVectorizer(
        stop_words="english",
        max_features=30000,
        ngram_range=(1, 2),
        min_df=2,
        max_df=0.95,
        sublinear_tf=True
    )

    X_train_vec = (
        vectorizer.fit_transform(
            X_train
        )
    )

    X_test_vec = (
        vectorizer.transform(
            X_test
        )
    )

    model = LogisticRegression(
        C=2.0,
        max_iter=2000,
        random_state=42
    )

    model.fit(
        X_train_vec,
        y_train
    )

    predictions = model.predict(
        X_test_vec
    )

    print("\n")
    print("=" * 70)
    print("LOCAL NEWS MODEL")
    print("=" * 70)

    print(
        f"Accuracy: "
        f"{accuracy_score(y_test, predictions) * 100:.2f}%"
    )

    print(
        f"Precision: "
        f"{precision_score(y_test, predictions, average='weighted', zero_division=0) * 100:.2f}%"
    )

    print(
        f"Recall: "
        f"{recall_score(y_test, predictions, average='weighted', zero_division=0) * 100:.2f}%"
    )

    print(
        f"F1: "
        f"{f1_score(y_test, predictions, average='weighted', zero_division=0) * 100:.2f}%"
    )

    print(
        "\nClassification Report:"
    )

    print(
        classification_report(
            y_test,
            predictions,
            zero_division=0
        )
    )

    joblib.dump(
        model,
        os.path.join(
            MODELS_DIR,
            "news_model.joblib"
        )
    )

    joblib.dump(
        vectorizer,
        os.path.join(
            MODELS_DIR,
            "news_vectorizer.joblib"
        )
    )

    metadata = {
        "text_column": text_column,
        "label_column": label_column,
        "classes": [
            str(x)
            for x in model.classes_
        ]
    }

    with open(
        os.path.join(
            MODELS_DIR,
            "news_metadata.json"
        ),
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            metadata,
            f,
            indent=4
        )

    print(
        "\n✓ News model saved."
    )

    return model


# ============================================================
# TRAIN REVIEW MODEL
# ============================================================

def train_review_model(
    review_path
):

    df = load_first_csv(
        review_path,
        "FAKE REVIEW DATASET"
    )

    df = clean_dataframe(
        df
    )

    text_column = find_column(
        df,
        [
            "text",
            "review",
            "review_text",
            "content",
            "comment"
        ]
    )

    label_column = find_column(
        df,
        [
            "label",
            "class",
            "target",
            "category",
            "fake",
            "is_fake"
        ]
    )

    print(
        "\nReview text column:",
        text_column
    )

    print(
        "Review label column:",
        label_column
    )

    if (
        text_column is None
        or label_column is None
    ):

        print(
            "\nCould not detect review columns."
        )

        print(
            "Available:",
            list(df.columns)
        )

        return None

    df = df.dropna(
        subset=[
            text_column,
            label_column
        ]
    )

    df["clean_text"] = (
        df[text_column]
        .apply(clean_text)
    )

    df = df[
        df["clean_text"].str.len() > 5
    ]

    df = df.drop_duplicates(
        subset=["clean_text"]
    )

    clean_file = os.path.join(
        CLEAN_DIR,
        "cleaned_reviews.csv"
    )

    df.to_csv(
        clean_file,
        index=False
    )

    X = df["clean_text"]
    y = df[label_column]

    X_train, X_test, y_train, y_test = (
        train_test_split(
            X,
            y,
            test_size=0.20,
            random_state=42,
            stratify=y
        )
    )

    vectorizer = TfidfVectorizer(
        stop_words="english",
        max_features=30000,
        ngram_range=(1, 2),
        min_df=2,
        max_df=0.95,
        sublinear_tf=True
    )

    X_train_vec = (
        vectorizer.fit_transform(
            X_train
        )
    )

    X_test_vec = (
        vectorizer.transform(
            X_test
        )
    )

    model = MultinomialNB(
        alpha=0.1
    )

    model.fit(
        X_train_vec,
        y_train
    )

    predictions = model.predict(
        X_test_vec
    )

    print("\n")
    print("=" * 70)
    print("LOCAL REVIEW MODEL")
    print("=" * 70)

    print(
        f"Accuracy: "
        f"{accuracy_score(y_test, predictions) * 100:.2f}%"
    )

    print(
        f"F1: "
        f"{f1_score(y_test, predictions, average='weighted', zero_division=0) * 100:.2f}%"
    )

    joblib.dump(
        model,
        os.path.join(
            MODELS_DIR,
            "review_model.joblib"
        )
    )

    joblib.dump(
        vectorizer,
        os.path.join(
            MODELS_DIR,
            "review_vectorizer.joblib"
        )
    )

    print(
        "\n✓ Review model saved."
    )

    return model


# ============================================================
# CLEAN CYBERSECURITY DATASET
# ============================================================

def clean_cybersecurity_dataset(
    cyber_path
):

    df = load_first_csv(
        cyber_path,
        "GLOBAL CYBERSECURITY THREATS 2015-2024"
    )

    df = clean_dataframe(
        df
    )

    output = os.path.join(
        CLEAN_DIR,
        "cleaned_cybersecurity.csv"
    )

    df.to_csv(
        output,
        index=False
    )

    print(
        "\n✓ Clean cybersecurity dataset saved:"
    )

    print(
        output
    )

    print(
        "\nColumns:"
    )

    for column in df.columns:

        print(
            " -",
            column
        )

    return df


# ============================================================
# DOWNLOAD PRETRAINED MODELS
# ============================================================

def download_pretrained_models():

    print("\n")
    print("=" * 70)
    print("DOWNLOADING PRETRAINED MODELS")
    print("=" * 70)

    paths = {}

    for name, model_id in (
        PRETRAINED_MODELS.items()
    ):

        print(
            f"\nDownloading {name}..."
        )

        try:

            path = kagglehub.model_download(
                model_id
            )

            paths[name] = path

            print(
                "✓",
                path
            )

        except Exception as e:

            print(
                "✗ Failed:",
                name
            )

            print(
                e
            )

    with open(
        os.path.join(
            PRETRAINED_DIR,
            "model_paths.json"
        ),
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            paths,
            f,
            indent=4
        )

    return paths


# ============================================================
# INSPECT MODEL DIRECTORY
# ============================================================

def inspect_model_directory(
    name,
    path
):

    print("\n")
    print(
        "-" * 70
    )

    print(
        "MODEL:",
        name
    )

    print(
        "-" * 70
    )

    for root, dirs, files in os.walk(
        path
    ):

        level = root.replace(
            path,
            ""
        ).count(os.sep)

        indent = "  " * level

        print(
            indent +
            os.path.basename(root) +
            "/"
        )

        for file in files:

            print(
                indent +
                "  └── " +
                file
            )


# ============================================================
# LABEL NORMALIZATION
# ============================================================

def normalize_news_label(
    label
):

    value = str(
        label
    ).strip().lower()

    if value in {
        "fake",
        "false",
        "1",
        "f",
        "fake news"
    }:

        return "Fake"

    if value in {
        "real",
        "true",
        "0",
        "r",
        "real news"
    }:

        return "Real"

    return "Unknown"


def normalize_review_label(
    label
):

    value = str(
        label
    ).strip().lower()

    if value in {
        "fake",
        "false",
        "1",
        "spam",
        "fraud"
    }:

        return "Fake"

    if value in {
        "genuine",
        "real",
        "true",
        "0",
        "authentic"
    }:

        return "Genuine"

    return "Unknown"


def normalize_phishing_label(
    label
):

    value = str(
        label
    ).strip().lower()

    if value in {
        "phishing",
        "phish",
        "malicious",
        "1",
        "true",
        "unsafe"
    }:

        return "Phishing"

    if value in {
        "safe",
        "legitimate",
        "benign",
        "0",
        "false"
    }:

        return "Safe"

    return "Unknown"


# ============================================================
# MODEL POLL
# ============================================================

def model_poll(
    predictions,
    task_name
):

    valid = [
        p for p in predictions
        if p is not None
        and p.get("label") != "Unknown"
    ]

    print("\n")
    print("=" * 70)

    print(
        f"{task_name.upper()} MODEL POLL"
    )

    print("=" * 70)

    if not valid:

        print(
            "\nNo valid model predictions."
        )

        return {
            "winner": "Unknown",
            "votes": {},
            "total": 0,
            "confidence": 0,
            "predictions": []
        }

    votes = Counter()

    for result in valid:

        model_name = result[
            "model"
        ]

        label = result[
            "label"
        ]

        votes[label] += 1

        confidence = result.get(
            "confidence"
        )

        if confidence is not None:

            print(
                f"{model_name:<40}"
                f" → {label:<12}"
                f" ({confidence * 100:.2f}%)"
            )

        else:

            print(
                f"{model_name:<40}"
                f" → {label}"
            )

    print("\nVote count:")

    for label, count in (
        votes.items()
    ):

        print(
            f"  {label}: {count}"
        )

    winner, count = (
        votes.most_common(1)[0]
    )

    total = sum(
        votes.values()
    )

    confidence = (
        count / total
    )

    print("\n" + "=" * 70)

    print(
        f"🏆 WINNER: {winner}"
    )

    print(
        f"Votes: {count}/{total}"
    )

    print(
        f"Vote confidence: "
        f"{confidence * 100:.2f}%"
    )

    print("=" * 70)

    return {
        "winner": winner,
        "votes": dict(votes),
        "winning_votes": count,
        "total": total,
        "confidence": confidence,
        "predictions": valid
    }


# ============================================================
# LOCAL NEWS PREDICTION
# ============================================================

def predict_local_news(
    text
):

    model = joblib.load(
        os.path.join(
            MODELS_DIR,
            "news_model.joblib"
        )
    )

    vectorizer = joblib.load(
        os.path.join(
            MODELS_DIR,
            "news_vectorizer.joblib"
        )
    )

    X = vectorizer.transform(
        [clean_text(text)]
    )

    raw = model.predict(
        X
    )[0]

    label = normalize_news_label(
        raw
    )

    confidence = None

    if hasattr(
        model,
        "predict_proba"
    ):

        confidence = float(
            np.max(
                model.predict_proba(X)[0]
            )
        )

    return {
        "model":
            "Local News Logistic Regression",
        "label":
            label,
        "confidence":
            confidence
    }


# ============================================================
# LOCAL REVIEW PREDICTION
# ============================================================

def predict_local_review(
    text
):

    model = joblib.load(
        os.path.join(
            MODELS_DIR,
            "review_model.joblib"
        )
    )

    vectorizer = joblib.load(
        os.path.join(
            MODELS_DIR,
            "review_vectorizer.joblib"
        )
    )

    X = vectorizer.transform(
        [clean_text(text)]
    )

    raw = model.predict(
        X
    )[0]

    label = normalize_review_label(
        raw
    )

    confidence = None

    if hasattr(
        model,
        "predict_proba"
    ):

        confidence = float(
            np.max(
                model.predict_proba(X)[0]
            )
        )

    return {
        "model":
            "Local Review Naive Bayes",
        "label":
            label,
        "confidence":
            confidence
    }


# ============================================================
# LOAD SKLEARN OBJECT
# ============================================================

def find_serialized_files(
    path
):

    files = []

    for pattern in [
        "*.joblib",
        "*.pkl",
        "*.pickle"
    ]:

        files.extend(
            glob.glob(
                os.path.join(
                    path,
                    "**",
                    pattern
                ),
                recursive=True
            )
        )

    return files


def load_prediction_model(
    path
):

    files = find_serialized_files(
        path
    )

    objects = []

    for file in files:

        try:

            obj = joblib.load(
                file
            )

            objects.append(
                (file, obj)
            )

        except Exception:
            pass

    return objects


# ============================================================
# GENERIC TEXT MODEL PREDICTION
# ============================================================

def predict_pretrained_text_model(
    objects,
    text,
    task,
    model_name
):

    for file, obj in objects:

        try:

            # ------------------------------------------------
            # Case 1:
            # sklearn Pipeline
            # ------------------------------------------------

            if hasattr(
                obj,
                "predict"
            ):

                prediction = obj.predict(
                    [text]
                )[0]

                if task == "news":

                    label = (
                        normalize_news_label(
                            prediction
                        )
                    )

                else:

                    label = (
                        normalize_review_label(
                            prediction
                        )
                    )

                confidence = None

                if hasattr(
                    obj,
                    "predict_proba"
                ):

                    try:

                        confidence = float(
                            np.max(
                                obj.predict_proba(
                                    [text]
                                )[0]
                            )
                        )

                    except Exception:
                        pass

                if label != "Unknown":

                    return {
                        "model":
                            model_name,
                        "label":
                            label,
                        "confidence":
                            confidence
                    }

        except Exception:
            continue

    return None


# ============================================================
# ARTICLE URL EXTRACTION
# ============================================================

def normalize_url(
    url
):

    url = url.strip()

    if not url.startswith(
        ("http://", "https://")
    ):

        url = (
            "https://" +
            url
        )

    return url


def extract_article_from_url(
    url
):

    url = normalize_url(
        url
    )

    print(
        "\nExtracting article:"
    )

    print(
        url
    )

    # --------------------------------------------------------
    # First try trafilatura
    # --------------------------------------------------------

    try:

        import trafilatura

        downloaded = (
            trafilatura.fetch_url(
                url
            )
        )

        if downloaded:

            text = (
                trafilatura.extract(
                    downloaded,
                    include_comments=False,
                    include_tables=False
                )
            )

            if text:

                return {
                    "url": url,
                    "text": text,
                    "title": ""
                }

    except Exception as e:

        print(
            "Trafilatura failed:",
            e
        )

    # --------------------------------------------------------
    # Fallback requests + BeautifulSoup
    # --------------------------------------------------------

    try:

        response = requests.get(
            url,
            timeout=15,
            headers={
                "User-Agent":
                    "Mozilla/5.0 "
                    "TrustGuard/1.0"
            }
        )

        response.raise_for_status()

        from bs4 import BeautifulSoup

        soup = BeautifulSoup(
            response.text,
            "html.parser"
        )

        title = ""

        if soup.title:

            title = (
                soup.title.get_text(
                    " ",
                    strip=True
                )
            )

        paragraphs = []

        for p in soup.find_all(
            "p"
        ):

            text = p.get_text(
                " ",
                strip=True
            )

            if len(text) > 30:

                paragraphs.append(
                    text
                )

        article_text = "\n".join(
            paragraphs
        )

        return {
            "url": url,
            "text": article_text,
            "title": title
        }

    except Exception as e:

        print(
            "URL extraction failed:",
            e
        )

        return {
            "url": url,
            "text": "",
            "title": ""
        }


# ============================================================
# GEMINI NEWS ENGINE
# ============================================================

class GeminiNewsEngine:

    def __init__(self):

        from google import genai

        api_key = os.getenv(
            "GEMINI_API_KEY"
        )

        if not api_key:

            raise RuntimeError(
                "GEMINI_API_KEY is not set."
            )

        self.client = genai.Client(
            api_key=api_key
        )

        self.model = os.getenv(
            "GEMINI_MODEL",
            "gemini-3.6-flash"
        )


    # ========================================================
    # NEWS VERIFICATION
    # ========================================================

    def verify_news(
        self,
        headline="",
        article_url="",
        article_text=""
    ):

        input_parts = []

        if headline:

            input_parts.append(
                f"HEADLINE:\n{headline}"
            )

        if article_url:

            input_parts.append(
                f"ARTICLE URL:\n{article_url}"
            )

        if article_text:

            # Keep enormous articles from
            # unnecessarily consuming input.
            input_parts.append(
                "ARTICLE TEXT:\n" +
                article_text[:30000]
            )

        evidence = "\n\n".join(
            input_parts
        )

        prompt = f"""
You are the web-verification model inside
Trust Guard.

Your job is to independently investigate a
news claim.

INPUT:

{evidence}

Use Google Search to find current and relevant
information.

If an ARTICLE URL is supplied, use URL Context
to inspect the supplied article.

Compare the submitted claim against:
- reputable news organizations
- government sources
- official organizations
- primary sources
- universities/research institutions
- multiple independent reports

Do not decide that something is false simply
because you cannot find it.

You must provide one voting label:

REAL
or
FAKE

IMPORTANT:
This is a model vote, not an absolute statement
of truth.

Return:

LABEL: REAL or FAKE

REASON:
Explain the evidence briefly.

CLAIM:
State the main claim being checked.

RELATED NEWS:
Identify up to 5 relevant sources.

SOURCE COMPARISON:
Explain whether the submitted article/headline
agrees or conflicts with the available sources.

UNCERTAINTY:
Mention important uncertainty if evidence is
incomplete.
"""

        try:

            interaction = (
                self.client
                .interactions
                .create(
                    model=self.model,
                    input=prompt,
                    tools=[
                        {
                            "type":
                                "google_search"
                        },
                        {
                            "type":
                                "url_context"
                        }
                    ]
                )
            )

            output = (
                interaction.output_text
            )

            label = (
                self.extract_label(
                    output
                )
            )

            citations = (
                self.extract_citations(
                    interaction
                )
            )

            return {
                "model":
                    "Gemini + Google Search",
                "label":
                    label,
                "text":
                    output,
                "citations":
                    citations
            }

        except Exception as e:

            print(
                "\nGemini verification failed:"
            )

            print(
                e
            )

            return {
                "model":
                    "Gemini + Google Search",
                "label":
                    "Unknown",
                "text":
                    str(e),
                "citations":
                    []
            }


    # ========================================================
    # LABEL EXTRACTION
    # ========================================================

    @staticmethod
    def extract_label(
        text
    ):

        match = re.search(
            r"LABEL\s*:\s*(REAL|FAKE)",
            text.upper()
        )

        if not match:

            return "Unknown"

        return (
            "Real"
            if match.group(1) == "REAL"
            else "Fake"
        )


    # ========================================================
    # CITATION EXTRACTION
    # ========================================================

    @staticmethod
    def extract_citations(
        interaction
    ):

        sources = []

        try:

            for step in (
                getattr(
                    interaction,
                    "steps",
                    []
                )
            ):

                if getattr(
                    step,
                    "type",
                    None
                ) != "model_output":

                    continue

                for block in (
                    getattr(
                        step,
                        "content",
                        []
                    )
                ):

                    annotations = (
                        getattr(
                            block,
                            "annotations",
                            []
                        )
                    )

                    for annotation in (
                        annotations
                    ):

                        if getattr(
                            annotation,
                            "type",
                            None
                        ) == "url_citation":

                            url = getattr(
                                annotation,
                                "url",
                                ""
                            )

                            title = getattr(
                                annotation,
                                "title",
                                ""
                            )

                            if url:

                                sources.append({
                                    "title":
                                        title,
                                    "url":
                                        url
                                })

        except Exception as e:

            print(
                "Citation extraction warning:",
                e
            )

        # Remove duplicates
        unique = []

        seen = set()

        for source in sources:

            if source["url"] not in seen:

                unique.append(
                    source
                )

                seen.add(
                    source["url"]
                )

        return unique


    # ========================================================
    # TRANSLATION
    # ========================================================

    def translate(
        self,
        text,
        language
    ):

        prompt = f"""
Translate the following news content into
{language}.

Preserve exactly:
- names
- organizations
- dates
- numbers
- places
- factual meaning

Do not add facts.

CONTENT:

{text}
"""

        try:

            interaction = (
                self.client
                .interactions
                .create(
                    model=self.model,
                    input=prompt
                )
            )

            return (
                interaction.output_text
            )

        except Exception as e:

            return (
                f"Translation failed: {e}"
            )


    # ========================================================
    # SUMMARY
    # ========================================================

    def summarize(
        self,
        text,
        language="English"
    ):

        prompt = f"""
Summarize this news in {language}.

Provide:
1. Headline
2. Three key points
3. Important people/organizations
4. Important dates/numbers
5. Neutral summary

Do not invent facts.

NEWS:

{text}
"""

        try:

            interaction = (
                self.client
                .interactions
                .create(
                    model=self.model,
                    input=prompt
                )
            )

            return (
                interaction.output_text
            )

        except Exception as e:

            return (
                f"Summary failed: {e}"
            )


# ============================================================
# FAKE NEWS ANALYSIS
# ============================================================

def analyze_fake_news(
    headline="",
    article_url="",
    article_text="",
    pretrained_paths=None
):

    print("\n")
    print("=" * 70)
    print("                    FAKE NEWS CHECK")
    print("=" * 70)

    # --------------------------------------------------------
    # Normalize URL
    # --------------------------------------------------------

    if article_url:

        article_url = normalize_url(
            article_url
        )

    # --------------------------------------------------------
    # If URL exists but text doesn't,
    # extract article.
    # --------------------------------------------------------

    extracted = {}

    if article_url:

        extracted = (
            extract_article_from_url(
                article_url
            )
        )

        if not article_text:

            article_text = (
                extracted.get(
                    "text",
                    ""
                )
            )

        if not headline:

            headline = (
                extracted.get(
                    "title",
                    ""
                )
            )

    # --------------------------------------------------------
    # Build ML input
    # --------------------------------------------------------

    ml_input = ""

    if headline:

        ml_input += (
            headline +
            "\n"
        )

    if article_text:

        ml_input += (
            article_text
        )

    # --------------------------------------------------------
    # Model predictions
    # --------------------------------------------------------

    predictions = []

    # --------------------------------------------------------
    # LOCAL MODEL
    # --------------------------------------------------------

    if ml_input.strip():

        try:

            local_result = (
                predict_local_news(
                    ml_input
                )
            )

            predictions.append(
                local_result
            )

        except Exception as e:

            print(
                "Local news model failed:",
                e
            )

    # --------------------------------------------------------
    # KAGGLE PRETRAINED FAKE NEWS MODEL
    # --------------------------------------------------------

    if pretrained_paths:

        path = pretrained_paths.get(
            "fake_news_model"
        )

        if path:

            objects = (
                load_prediction_model(
                    path
                )
            )

            if ml_input.strip():

                result = (
                    predict_pretrained_text_model(
                        objects,
                        ml_input,
                        "news",
                        "Kaggle Fake News Model"
                    )
                )

                if result:

                    predictions.append(
                        result
                    )

                else:

                    print(
                        "\nKaggle Fake News Model "
                        "could not accept the supplied "
                        "text interface."
                    )

    # --------------------------------------------------------
    # GEMINI + WEB
    # --------------------------------------------------------

    gemini_result = None
    gemini = None

    try:

        gemini = (
            GeminiNewsEngine()
        )

        gemini_result = (
            gemini.verify_news(
                headline=headline,
                article_url=article_url,
                article_text=article_text
            )
        )

        predictions.append({
            "model":
                gemini_result["model"],
            "label":
                gemini_result["label"],
            "confidence":
                None
        })

    except Exception as e:

        print(
            "\nGemini unavailable:",
            e
        )

    # --------------------------------------------------------
    # FINAL POLL
    # --------------------------------------------------------

    poll = model_poll(
        predictions,
        "Fake News"
    )

    # --------------------------------------------------------
    # RESULT
    # --------------------------------------------------------

    print("\n")
    print("=" * 70)
    print("                 FINAL NEWS RESULT")
    print("=" * 70)

    print(
        f"\n🏆 FINAL RESULT: "
        f"{poll['winner']}"
    )

    print(
        f"Vote confidence: "
        f"{poll['confidence'] * 100:.2f}%"
    )

    # --------------------------------------------------------
    # WEB SOURCES
    # --------------------------------------------------------

    if gemini_result:

        print("\n")
        print("=" * 70)
        print("RELATED NEWS / WEB EVIDENCE")
        print("=" * 70)

        print(
            gemini_result.get(
                "text",
                ""
            )
        )

        sources = (
            gemini_result.get(
                "citations",
                []
            )
        )

        if sources:

            print("\nSources:")

            for index, source in enumerate(
                sources,
                1
            ):

                print(
                    f"{index}. "
                    f"{source['title']}"
                )

                print(
                    f"   {source['url']}"
                )

    return {
        "headline":
            headline,

        "article_url":
            article_url,

        "poll":
            poll,

        "gemini":
            gemini_result
    }


# ============================================================
# PHISHING URL FEATURES
# ============================================================

def extract_url_features(
    url
):

    url = normalize_url(
        url
    )

    parsed = urlparse(
        url
    )

    hostname = (
        parsed.hostname or ""
    )

    lower = url.lower()

    # HTTPS
    https = int(
        parsed.scheme == "https"
    )

    # Suspicious keywords
    suspicious_keywords = [
        "login",
        "signin",
        "verify",
        "verification",
        "update",
        "account",
        "secure",
        "security",
        "bank",
        "paypal",
        "wallet",
        "crypto",
        "password",
        "credential",
        "confirm",
        "authentication",
        "auth",
        "recover",
        "unlock"
    ]

    suspicious_keyword = int(
        any(
            word in lower
            for word in suspicious_keywords
        )
    )

    # Special characters
    special_chars = set(
        "-.?=&@_%#"
    )

    special_count = sum(
        1
        for c in url
        if c in special_chars
    )

    # Suspicious TLD
    suspicious_tlds = [
        ".xyz",
        ".info",
        ".top",
        ".click",
        ".date",
        ".win",
        ".party",
        ".cc",
        ".loan",
        ".live",
        ".online",
        ".site",
        ".work"
    ]

    suspicious_tld = int(
        any(
            hostname.endswith(tld)
            for tld in suspicious_tlds
        )
    )

    # URL length
    url_length = len(url)

    # Hostname length
    hostname_length = len(
        hostname
    )

    # Number of dots
    dot_count = url.count(".")

    # Number of hyphens
    hyphen_count = url.count("-")

    # Number of digits
    digit_count = sum(
        c.isdigit()
        for c in url
    )

    # Number of subdomains
    subdomain_count = max(
        0,
        len(
            hostname.split(".")
        ) - 2
    )

    # IP address
    ip_address = int(
        bool(
            re.fullmatch(
                r"\d{1,3}(\.\d{1,3}){3}",
                hostname
            )
        )
    )

    # @ symbol
    at_symbol = int(
        "@" in url
    )

    # Query
    has_query = int(
        bool(parsed.query)
    )

    return [
        https,
        suspicious_keyword,
        special_count,
        suspicious_tld,
        url_length,
        hostname_length,
        dot_count,
        hyphen_count,
        digit_count,
        subdomain_count,
        ip_address,
        at_symbol,
        has_query
    ]


# ============================================================
# LOCAL PHISHING MODEL
# ============================================================

def train_local_phishing_model():

    # Small fallback dataset.
    # For production, replace with a large labelled
    # phishing URL dataset.

    urls = [

        # SAFE
        ("https://www.google.com", 0),
        ("https://github.com", 0),
        ("https://www.wikipedia.org", 0),
        ("https://www.amazon.com", 0),
        ("https://www.microsoft.com", 0),
        ("https://www.linkedin.com", 0),
        ("https://www.netflix.com", 0),
        ("https://www.apple.com", 0),
        ("https://www.nytimes.com", 0),
        ("https://www.cnn.com", 0),

        # PHISHING
        (
            "http://verify-paypal-account-security.xyz/login",
            1
        ),

        (
            "http://secure-bank-update.info/login.php",
            1
        ),

        (
            "http://netflix-secure-update.top/login",
            1
        ),

        (
            "http://wallet-crypto-connect.click/index.html",
            1
        ),

        (
            "http://signin-google-account-verify.win/auth",
            1
        ),

        (
            "https://secure-bank-login-page-verification-update.cc/verify",
            1
        ),

        (
            "http://claim-free-btc-reward.party/spin",
            1
        ),

        (
            "http://update-microsoft-office-security.date/login",
            1
        ),

        (
            "http://verify-your-identity-paypal.xyz/auth",
            1
        ),

        (
            "http://free-giftcard-deals.click/redeem",
            1
        )
    ]

    X = np.array([
        extract_url_features(url)
        for url, label in urls
    ])

    y = np.array([
        label
        for url, label in urls
    ])

    model = RandomForestClassifier(
        n_estimators=300,
        max_depth=10,
        class_weight="balanced",
        random_state=42
    )

    model.fit(
        X,
        y
    )

    path = os.path.join(
        MODELS_DIR,
        "local_phishing_model.joblib"
    )

    joblib.dump(
        model,
        path
    )

    print(
        "\n✓ Local phishing model saved."
    )

    return model


# ============================================================
# LOCAL PHISHING PREDICTION
# ============================================================

def predict_local_phishing(
    url
):

    path = os.path.join(
        MODELS_DIR,
        "local_phishing_model.joblib"
    )

    if not os.path.exists(path):

        train_local_phishing_model()

    model = joblib.load(
        path
    )

    features = np.array(
        [
            extract_url_features(url)
        ],
        dtype=float
    )

    prediction = model.predict(
        features
    )[0]

    phishing_probability = None

    if hasattr(
        model,
        "predict_proba"
    ):

        probabilities = (
            model.predict_proba(
                features
            )[0]
        )

        if 1 in list(
            model.classes_
        ):

            index = list(
                model.classes_
            ).index(1)

            phishing_probability = (
                float(
                    probabilities[index]
                )
            )

    label = (
        "Phishing"
        if prediction == 1
        else "Safe"
    )

    return {
        "model":
            "Local URL Random Forest",

        "label":
            label,

        "confidence":
            (
                phishing_probability
                if label == "Phishing"
                else (
                    1 -
                    phishing_probability
                    if phishing_probability
                    is not None
                    else None
                )
            )
    }


# ============================================================
# LOAD BERTPHISH
# ============================================================

def load_bertphish(
    model_path
):

    try:

        from transformers import (
            AutoTokenizer,
            AutoModelForSequenceClassification
        )

        tokenizer = (
            AutoTokenizer.from_pretrained(
                model_path
            )
        )

        model = (
            AutoModelForSequenceClassification
            .from_pretrained(
                model_path
            )
        )

        model.eval()

        print(
            "\n✓ BERTPhish loaded."
        )

        print(
            "Labels:",
            model.config.id2label
        )

        return tokenizer, model

    except Exception as e:

        print(
            "\nBERTPhish could not load:"
        )

        print(
            e
        )

        return None, None


# ============================================================
# BERTPHISH PREDICTION
# ============================================================

def predict_bertphish(
    url,
    tokenizer,
    model
):

    try:

        import torch

        inputs = tokenizer(
            url,
            return_tensors="pt",
            truncation=True,
            max_length=256,
            padding=True
        )

        with torch.no_grad():

            output = model(
                **inputs
            )

        probabilities = torch.softmax(
            output.logits,
            dim=-1
        )[0]

        class_id = int(
            torch.argmax(
                probabilities
            ).item()
        )

        confidence = float(
            probabilities[
                class_id
            ].item()
        )

        raw_label = str(
            model.config.id2label.get(
                class_id,
                ""
            )
        )

        lower = raw_label.lower()

        if any(
            x in lower
            for x in [
                "phish",
                "malicious",
                "unsafe",
                "attack"
            ]
        ):

            label = "Phishing"

        elif any(
            x in lower
            for x in [
                "safe",
                "benign",
                "legitimate",
                "normal"
            ]
        ):

            label = "Safe"

        else:

            # Do not guess when model labels
            # are unknown.
            print(
                "\nUnknown BERTPhish label:",
                raw_label
            )

            return None

        return {
            "model":
                "BERTPhish",

            "label":
                label,

            "confidence":
                confidence
        }

    except Exception as e:

        print(
            "\nBERTPhish prediction error:",
            e
        )

        return None


# ============================================================
# KAGGLE RANDOM FOREST PHISHING
# ============================================================

def predict_kaggle_phishing_rf(
    model,
    url
):

    try:

        expected = getattr(
            model,
            "n_features_in_",
            None
        )

        features = (
            extract_url_features(
                url
            )
        )

        # IMPORTANT:
        # Only use our extractor if it matches
        # the downloaded model's expected dimensions.

        if expected is None:

            print(
                "\nKaggle RF skipped:"
                " n_features_in_ unavailable."
            )

            return None

        if expected != len(
            features
        ):

            print(
                "\nKaggle RF skipped:"
            )

            print(
                f"Model expects "
                f"{expected} features."
            )

            print(
                f"Our extractor has "
                f"{len(features)} features."
            )

            return None

        X = np.array(
            [features],
            dtype=float
        )

        prediction = model.predict(
            X
        )[0]

        label = (
            normalize_phishing_label(
                prediction
            )
        )

        if label == "Unknown":

            return None

        confidence = None

        if hasattr(
            model,
            "predict_proba"
        ):

            confidence = float(
                np.max(
                    model.predict_proba(
                        X
                    )[0]
                )
            )

        return {
            "model":
                "Kaggle Phishing Random Forest",

            "label":
                label,

            "confidence":
                confidence
        }

    except Exception as e:

        print(
            "\nKaggle phishing RF failed:",
            e
        )

        return None


# ============================================================
# PHISHING ANALYSIS
# ============================================================

def analyze_phishing(
    url,
    pretrained_paths
):

    url = normalize_url(
        url
    )

    predictions = []

    print("\n")
    print("=" * 70)
    print("                    PHISHING CHECK")
    print("=" * 70)

    print(
        "\nURL:",
        url
    )

    # --------------------------------------------------------
    # Local RF
    # --------------------------------------------------------

    try:

        result = (
            predict_local_phishing(
                url
            )
        )

        predictions.append(
            result
        )

    except Exception as e:

        print(
            "Local phishing model error:",
            e
        )

    # --------------------------------------------------------
    # Kaggle RF
    # --------------------------------------------------------

    rf_path = (
        pretrained_paths.get(
            "phishing_random_forest"
        )
    )

    if rf_path:

        objects = (
            load_prediction_model(
                rf_path
            )
        )

        # Find a model with predict()
        for file, obj in objects:

            if hasattr(
                obj,
                "predict"
            ):

                result = (
                    predict_kaggle_phishing_rf(
                        obj,
                        url
                    )
                )

                if result:

                    predictions.append(
                        result
                    )

                    break

    # --------------------------------------------------------
    # BERTPhish
    # --------------------------------------------------------

    bert_path = (
        pretrained_paths.get(
            "bertphish"
        )
    )

    if bert_path:

        tokenizer, model = (
            load_bertphish(
                bert_path
            )
        )

        if (
            tokenizer is not None
            and model is not None
        ):

            result = (
                predict_bertphish(
                    url,
                    tokenizer,
                    model
                )
            )

            if result:

                predictions.append(
                    result
                )

    # --------------------------------------------------------
    # Poll
    # --------------------------------------------------------

    poll = model_poll(
        predictions,
        "Phishing"
    )

    return poll


# ============================================================
# FAKE REVIEW ANALYSIS
# ============================================================

def analyze_fake_review(
    review,
    pretrained_paths
):

    predictions = []

    # Local
    try:

        predictions.append(
            predict_local_review(
                review
            )
        )

    except Exception as e:

        print(
            "Local review model error:",
            e
        )

    # Kaggle
    path = (
        pretrained_paths.get(
            "fake_review_model"
        )
    )

    if path:

        objects = (
            load_prediction_model(
                path
            )
        )

        result = (
            predict_pretrained_text_model(
                objects,
                review,
                "review",
                "Kaggle Fake Review Model"
            )
        )

        if result:

            predictions.append(
                result
            )

    return model_poll(
        predictions,
        "Fake Review"
    )


# ============================================================
# TRANSLATION / SUMMARY MENU
# ============================================================

def optional_news_tools(
    headline,
    article_text,
    gemini
):

    if gemini is None:

        return

    content = (
        headline +
        "\n\n" +
        article_text
    ).strip()

    if not content:

        return

    print("\n")
    print("=" * 70)
    print("ADDITIONAL NEWS TOOLS")
    print("=" * 70)

    print(
        "\n1. Translate"
    )

    print(
        "2. Summarize"
    )

    print(
        "3. Skip"
    )

    choice = input(
        "\nChoose: "
    ).strip()

    if choice == "1":

        language = input(
            "Enter language: "
        ).strip()

        if language:

            result = gemini.translate(
                content,
                language
            )

            print(
                "\nTRANSLATION:"
            )

            print(
                result
            )

    elif choice == "2":

        language = input(
            "Summary language "
            "(default English): "
        ).strip()

        if not language:

            language = "English"

        result = gemini.summarize(
            content,
            language
        )

        print(
            "\nSUMMARY:"
        )

        print(
            result
        )


# ============================================================
# NEWS INPUT MENU
# ============================================================

def news_input_menu(
    pretrained_paths
):

    print("\n")
    print("=" * 70)
    print("                    NEWS CHECK")
    print("=" * 70)

    print(
        "\nChoose input:"
    )

    print(
        "1. Headline only"
    )

    print(
        "2. Article URL only"
    )

    print(
        "3. Headline + Article URL"
    )

    choice = input(
        "\nChoice: "
    ).strip()

    headline = ""
    url = ""
    article_text = ""

    # --------------------------------------------------------
    # HEADLINE
    # --------------------------------------------------------

    if choice == "1":

        headline = input(
            "\nEnter headline:\n"
        ).strip()

    # --------------------------------------------------------
    # URL
    # --------------------------------------------------------

    elif choice == "2":

        url = input(
            "\nEnter article URL:\n"
        ).strip()

        extracted = (
            extract_article_from_url(
                url
            )
        )

        headline = extracted.get(
            "title",
            ""
        )

        article_text = extracted.get(
            "text",
            ""
        )

    # --------------------------------------------------------
    # BOTH
    # --------------------------------------------------------

    elif choice == "3":

        headline = input(
            "\nEnter headline:\n"
        ).strip()

        url = input(
            "\nEnter article URL:\n"
        ).strip()

        extracted = (
            extract_article_from_url(
                url
            )
        )

        article_text = extracted.get(
            "text",
            ""
        )

    else:

        print(
            "Invalid choice."
        )

        return

    if not headline and not url:

        print(
            "\nNo input supplied."
        )

        return

    # --------------------------------------------------------
    # Analyze
    # --------------------------------------------------------

    result = analyze_fake_news(
        headline=headline,
        article_url=url,
        article_text=article_text,
        pretrained_paths=pretrained_paths
    )

    # --------------------------------------------------------
    # Additional tools
    # --------------------------------------------------------

    try:

        gemini = (
            GeminiNewsEngine()
        )

        optional_news_tools(
            headline,
            article_text,
            gemini
        )

    except Exception:

        pass

    return result


# ============================================================
# MAIN MENU
# ============================================================

def main_menu(
    pretrained_paths
):

    while True:

        print("\n")
        print("=" * 70)
        print("                    TRUST GUARD")
        print("=" * 70)

        print(
            "\n1. Fake News Detection"
        )

        print(
            "2. Fake Review Detection"
        )

        print(
            "3. Phishing URL Detection"
        )

        print(
            "4. Exit"
        )

        choice = input(
            "\nEnter choice: "
        ).strip()

        # ----------------------------------------------------
        # NEWS
        # ----------------------------------------------------

        if choice == "1":

            news_input_menu(
                pretrained_paths
            )

        # ----------------------------------------------------
        # REVIEW
        # ----------------------------------------------------

        elif choice == "2":

            review = input(
                "\nEnter review:\n"
            ).strip()

            if review:

                analyze_fake_review(
                    review,
                    pretrained_paths
                )

        # ----------------------------------------------------
        # PHISHING
        # ----------------------------------------------------

        elif choice == "3":

            url = input(
                "\nEnter URL:\n"
            ).strip()

            if url:

                analyze_phishing(
                    url,
                    pretrained_paths
                )

        # ----------------------------------------------------
        # EXIT
        # ----------------------------------------------------

        elif choice == "4":

            print(
                "\nGoodbye."
            )

            break

        else:

            print(
                "\nInvalid choice."
            )


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    print("\n")
    print("=" * 70)
    print("                  TRUST GUARD")
    print("=" * 70)
    print(
        "AI-Powered Fake News, Fake Review "
        "and Phishing Detection"
    )
    print("=" * 70)

    # --------------------------------------------------------
    # Download datasets
    # --------------------------------------------------------

    paths = download_datasets()

    NEWS_PATH = paths["news"]
    REVIEW_PATH = paths["reviews"]
    CYBER_PATH = paths["cyber"]

    # --------------------------------------------------------
    # Train local models
    # --------------------------------------------------------

    print("\nTraining local news model...")

    train_news_model(
        NEWS_PATH
    )

    print("\nTraining local review model...")

    train_review_model(
        REVIEW_PATH
    )

    print("\nCleaning cybersecurity dataset...")

    clean_cybersecurity_dataset(
        CYBER_PATH
    )

    print(
        "\nTraining local phishing model..."
    )

    train_local_phishing_model()

    # --------------------------------------------------------
    # Download pretrained models
    # --------------------------------------------------------

    pretrained_paths = (
        download_pretrained_models()
    )

    # --------------------------------------------------------
    # Inspect models
    # --------------------------------------------------------

    print("\n")
    print("=" * 70)
    print("PRETRAINED MODEL FILES")
    print("=" * 70)

    for name, path in (
        pretrained_paths.items()
    ):

        inspect_model_directory(
            name,
            path
        )

    # --------------------------------------------------------
    # Start application
    # --------------------------------------------------------

    main_menu(
        pretrained_paths
    )