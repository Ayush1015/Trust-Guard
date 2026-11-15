"""Grounded sanity battery for the local NLI entailment model.

Runs the REAL ONNX model (models/nli/) against hand-built cases with known
correct relations: plain support/refute, neutral, negation, numeric
mismatch, date mismatch, and paraphrase. This is a qualification gate for
the model as used by services/entailment_service.py - it shows the model
handles the relation types TrustGuard relies on. It does NOT establish
real-world fact-checking accuracy (the model compares texts; it does not
know what is true).

Run:  python3 training/test_nli_entailment.py
Needs: models/nli/ artifacts + onnxruntime + tokenizers installed.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.expanduser(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from services.entailment_service import _nli_batch, is_available  # noqa: E402

# (premise, hypothesis, expected top label)
CASES = [
    # plain support
    ("The Eiffel Tower is located in Paris, France.",
     "The Eiffel Tower is in Paris.", "entailment"),
    ("Officials said 40 people died in the earthquake.",
     "The earthquake killed 40 people.", "entailment"),
    ("Heavy rain caused flooding in Jakarta on Tuesday.",
     "Flooding hit Jakarta.", "entailment"),
    # paraphrase support
    ("The central bank raised interest rates by half a percentage point.",
     "Interest rates went up.", "entailment"),
    # plain refute
    ("The Eiffel Tower is located in Paris, France.",
     "The Eiffel Tower is in Berlin.", "contradiction"),
    # negation
    ("The vaccine does not contain any microchips.",
     "The vaccine contains microchips.", "contradiction"),
    ("The mayor said the festival was cancelled.",
     "The festival will go ahead as planned.", "contradiction"),
    # numeric mismatch
    ("The company reported revenue of $2 billion in 2019.",
     "The company reported revenue of $3 billion.", "contradiction"),
    # date mismatch
    ("The president signed the bill on Monday.",
     "The president signed the bill on Tuesday.", "contradiction"),
    # neutral: related topic, but the claim is not settled by the premise
    ("The Eiffel Tower is located in Paris, France.",
     "The Eiffel Tower is the tallest structure in France.", "neutral"),
    ("The team won the championship in 2019.",
     "The team will win the championship next year.", "neutral"),
]


def main() -> int:
    if not is_available():
        print("NLI model not available - models/nli/ artifacts missing?")
        return 2

    scores = [_nli_batch([p], h)[0] for p, h, _ in CASES]

    passed = 0
    for (premise, hypothesis, expected), probs in zip(CASES, scores):
        if not probs:
            print(f"FAIL no-scores  P: {premise}")
            continue
        top = max(probs, key=probs.get)
        ok = top == expected
        passed += ok
        print(
            f"{'PASS' if ok else 'FAIL'} expect={expected:14s} "
            f"got={top:14s} "
            f"(e={probs.get('entailment', 0):.3f} "
            f"n={probs.get('neutral', 0):.3f} "
            f"c={probs.get('contradiction', 0):.3f})"
        )
        if not ok:
            print(f"     P: {premise}\n     H: {hypothesis}")

    print(f"\n{passed}/{len(CASES)} correct")
    return 0 if passed == len(CASES) else 1


if __name__ == "__main__":
    raise SystemExit(main())
