"""Bootstrap the local NLI model files into models/nli/.

Source: cross-encoder/nli-MiniLM2-L6-H768 (Apache-2.0), downloaded from
Hugging Face Hub. The repo ships the official onnx/model_quint8_avx2.onnx
export, so no local quantization step is needed. Verifies every file is
non-empty; run training/test_nli_entailment.py afterwards for a grounded
behavioral check.

Usage: python training/bootstrap_nli.py [--dest DIR]
"""
import argparse
import hashlib
import sys
import urllib.request
from pathlib import Path

REPO = "cross-encoder/nli-MiniLM2-L6-H768"
REVISION = "b95119ce93d3e065de6214e38cd4a97b0f2f2c6d"
BASE = f"https://huggingface.co/{REPO}/resolve/{REVISION}/"
SHA256 = {'special_tokens_map.json': '378eb3bf733eb16e65792d7e3fda5b8a4631387ca04d2015199c4d4f22ae554d', 'config.json': '8b0e41caff7567c0f53e6983f35591c3dec59507c9173ab125c5823394fb57f3', 'tokenizer.json': '82139106e603ee4e1d5bc99d056ccbed5a92bc24848b1b5a7137c26e00d0dbf6', 'model_quint8_avx2.onnx': '44391a5241a62e0083c1a8899a71e69a092b95aea5ba89e14062925468eceac7', 'tokenizer_config.json': 'e06f5c3c435fc0255b08b5574cd574eec685390f60c85b27f83d785eb8ecaaa1', 'merges.txt': 'fe36cab26d4f4421ed725e10a2e9ddb7f799449c603a96e7f29b5a3c82a95862', 'vocab.json': 'ed19656ea1707df69134c4af35c8ceda2cc9860bf2c3495026153a133670ab5e'}
FILES = [
    ("onnx/model_quint8_avx2.onnx", "model_quint8_avx2.onnx"),
    ("tokenizer.json", "tokenizer.json"),
    ("tokenizer_config.json", "tokenizer_config.json"),
    ("config.json", "config.json"),
    ("vocab.json", "vocab.json"),
    ("merges.txt", "merges.txt"),
    ("special_tokens_map.json", "special_tokens_map.json"),
]

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dest", default=str(Path(__file__).resolve().parents[1] / "models" / "nli"))
    dest = Path(ap.parse_args().dest)
    dest.mkdir(parents=True, exist_ok=True)
    for remote, local in FILES:
        target = dest / local
        url = BASE + remote
        print(f"downloading {url} -> {target}")
        with urllib.request.urlopen(url, timeout=120) as r:
            data = r.read()
        if hashlib.sha256(data).hexdigest() != SHA256[local]:
            raise ValueError(f"SHA-256 mismatch for {local}; refusing model installation")
        temporary = target.with_suffix(target.suffix + ".tmp")
        temporary.write_bytes(data)
        temporary.replace(target)
        if target.stat().st_size == 0:
            print(f"FAILED: {target} is empty", file=sys.stderr)
            return 1
    print(f"OK: {len(FILES)} files in {dest} (Apache-2.0, {REPO})")
    print("next: python training/test_nli_entailment.py")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
