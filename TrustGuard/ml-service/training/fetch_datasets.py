"""Fetch the external datasets used by the v2 training scripts.

Writes into <ml-service>/datasets/ (override with TG_DATA_DIR):
- PhiUSIIL_Phishing_URL_Dataset.csv  - UCI ML Repository dataset 967, CC BY 4.0
  (attribution: Prasad, A. & Chandra, S. (2024), PhiUSIIL Phishing URL Dataset)
- arijit_reviews.parquet           - theArijitDas/Fake-Reviews-Dataset (HF,
  Apache-2.0 processing of Salminen et al. 2022 corpus, upstream OSF CC BY 4.0)
- flowerly_{train,validation,test}.parquet - Flowerly/modern-fake-reviews (CC BY 4.0)

The Kaggle fake-news CSV for train_news_v2.py is NOT fetched here: its exact
corpus and license are unverified. Supply your own CSV via TG_NEWS_CSV.
"""
import os
import sys
import urllib.request
import zipfile
from io import BytesIO
from pathlib import Path

DEST = Path(os.getenv("TG_DATA_DIR", str(Path(__file__).resolve().parents[1] / "datasets")))
UCI_ZIP = "https://archive.ics.uci.edu/static/public/967/phiusiil+phishing+url+dataset.zip"
HF = "https://huggingface.co/datasets/{repo}/resolve/main/{path}"
JOBS = [
    (UCI_ZIP, "zip:PhiUSIIL_Phishing_URL_Dataset.csv", "PhiUSIIL_Phishing_URL_Dataset.csv"),
    (HF.format(repo="theArijitDas/Fake-Reviews-Dataset", path="data/train-00000-of-00001.parquet"), None, "arijit_reviews.parquet"),
    (HF.format(repo="Flowerly/modern-fake-reviews", path="data/train-00000-of-00001.parquet"), None, "flowerly_train.parquet"),
    (HF.format(repo="Flowerly/modern-fake-reviews", path="data/validation-00000-of-00001.parquet"), None, "flowerly_validation.parquet"),
    (HF.format(repo="Flowerly/modern-fake-reviews", path="data/test-00000-of-00001.parquet"), None, "flowerly_test.parquet"),
]

def main() -> int:
    DEST.mkdir(parents=True, exist_ok=True)
    for url, zip_member, name in JOBS:
        target = DEST / name
        print(f"downloading {url} -> {target}")
        with urllib.request.urlopen(url, timeout=300) as r:
            data = r.read()
        if zip_member:
            member = zip_member.split(":", 1)[1]
            with zipfile.ZipFile(BytesIO(data)) as z:
                data = z.read(member)
        target.write_bytes(data)
        if target.stat().st_size == 0:
            print(f"FAILED: {target} empty", file=sys.stderr)
            return 1
    print(f"OK: datasets in {DEST}")
    print("licenses: PhiUSIIL CC BY 4.0 (cite Prasad & Chandra 2024, UCI 967);")
    print("theArijitDas mirror Apache-2.0 / upstream Salminen et al. CC BY 4.0;")
    print("Flowerly/modern-fake-reviews CC BY 4.0")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
