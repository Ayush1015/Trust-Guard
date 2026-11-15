"""Regression harness for TrustGuard's model_poll ensemble aggregation.

Loads the ACTUAL function source from main.py (and from the pre-fix backup)
via ast extraction, execs it with stubbed dependencies, and checks behavior.
"""
import ast
import logging
import os
from collections import Counter
from typing import Any, Optional

ML = str(__import__("pathlib").Path(__file__).resolve().parents[1] / "main.py")
BAK = str(__import__("pathlib").Path(__file__).resolve().parent / "fixtures" / "original_poll.py")



def clamp01(value, default=0.5):
    try:
        x = float(value)
    except Exception:
        return default
    if x > 1.0:
        x /= 100.0
    return max(0.0, min(1.0, x))

def load_fn(path, name):
    tree = ast.parse(open(path).read())
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            seg = ast.get_source_segment(open(path).read(), node)
            ns = {
                "logger": logging.getLogger("test"),
                "Counter": Counter,
                "Any": Any,
                "Optional": Optional,
                "os": os, "clamp01": clamp01,
            }
            exec(seg, ns)
            return ns[name]
    raise RuntimeError(f"{name} not found in {path}")


old_poll = load_fn(BAK, "model_poll")
new_poll = load_fn(ML, "model_poll")


def pred(label, conf_pct, weight=1.0, name="M"):
    # make_prediction contract: confidence stored as 0-100 percentage
    return {
        "model": name,
        "label": label,
        "confidence": conf_pct,
        "weight": weight,
        "source": "ml",
        "status": "participated",
    }


results = {}


def check(name, cond, detail=""):
    results[name] = {"pass": bool(cond), "detail": detail}
    print(("PASS " if cond else "FAIL ") + name + (" | " + str(detail) if detail else ""))


# --- Defect reproduction on pre-fix code ---
old_single = old_poll([pred("Real", 73.0)], "Fake News")
check("defect_reproduced_old_code",
      old_single["confidence"] == 100.0,
      f"old confidence={old_single['confidence']} for single 73% voter (expected 100, the defect)")

# --- Fix verification ---
new_single = new_poll([pred("Real", 73.0)], "Fake News")
check("fix_single_voter_73",
      new_single["confidence"] == 73.0 and new_single["winner"] == "Real" and not new_single["abstain"],
      f"confidence={new_single['confidence']} abstain={new_single['abstain']}")

new_weak = new_poll([pred("Real", 51.0)], "Fake News")
check("weak_single_voter_abstains",
      new_weak["confidence"] == 51.0 and new_weak["abstain"] and "low_confidence" in new_weak["abstainReasons"]
      and new_weak["verdictStatus"] == "uncertain",
      f"confidence={new_weak['confidence']} reasons={new_weak['abstainReasons']}")

edge = new_poll([pred("Real", 1.0)], "Fake News")
check("one_percent_edge_not_read_as_100",
      edge["confidence"] == 1.0 and edge["abstain"],
      f"confidence={edge['confidence']}")

two = new_poll([pred("Real", 99.0, name="A"), pred("Fake", 51.0, name="B")], "Fake News")
# Real: 0.99 + 0.49 = 1.48 ; Fake: 0.01 + 0.51 = 0.52 ; total 2.0 -> 74.0
# 1-1 vote tie with unequal confidences (99% vs 51%) still abstains:
# confidences are uncalibrated and from different models, so they cannot
# break a vote tie. The aggregate remains a labeled heuristic.
check("two_voter_softvote",
      two["winner"] == "Real" and abs(two["confidence"] - 74.0) < 0.01
      and two["abstain"] and "tied_votes" in two["abstainReasons"] and two["isTie"],
      f"winner={two['winner']} confidence={two['confidence']} reasons={two['abstainReasons']}")

tie = new_poll([pred("Real", 70.0, name="A"), pred("Fake", 70.0, name="B")], "Fake News")
check("tie_abstains",
      tie["isTie"] and tie["abstain"] and "tied_scores" in tie["abstainReasons"],
      f"isTie={tie['isTie']} reasons={tie['abstainReasons']}")

empty = new_poll([], "Fake News")
check("empty_poll",
      empty["winner"] == "Unknown" and empty["abstain"] and empty["verdictStatus"] == "insufficient_evidence",
      "")

malformed = new_poll([{"model": "X", "label": "Real", "confidence": "junk", "status": "participated"},
                      pred("Fake", 80.0)], "Fake News")
check("malformed_skipped",
      malformed["totalVotes"] == 1 and malformed["winner"] == "Fake",
      f"totalVotes={malformed['totalVotes']}")

unan = new_poll([pred("Real", 90.0, name="A"), pred("Real", 80.0, name="B")], "Fake News")
# Real scores 0.9+0.8=1.7, complement 0.3, total 2.0 -> 85.0
check("unanimous_mean",
      abs(unan["confidence"] - 85.0) < 0.01 and unan["isUnanimous"]
      and unan["voteRatioConfidence"] == 100.0 and abs(unan["modelScoreConfidence"] - 85.0) < 0.01,
      f"confidence={unan['confidence']}")

multi = new_poll([pred("A", 60.0, name="a"), pred("B", 60.0, name="b"), pred("A", 40.0, name="c")], "Multi")
# Binary complement split: A gets .6+.4(spill from b)+.4 = 1.4 ; B gets .4+.6+.6(spill from c) = 1.6
# total 3.0 -> B share 53.33. A 40%-confidence vote for A is 60% evidence for B.
check("multilabel_complement_split",
      multi["winner"] == "B" and abs(multi["confidence"] - 53.33) < 0.01 and multi["abstain"],
      f"winner={multi['winner']} confidence={multi['confidence']}")

keys = set(new_poll([pred("Real", 80.0)], "t").keys())
legacy = {"winner", "votes", "weightedVotes", "weightedSharePercent", "totalVotes",
          "winningVotes", "confidence", "voteRatioConfidence", "weightedConfidence",
          "margin", "runnerUp", "isUnanimous", "isTie", "models", "task"}
check("legacy_keys_preserved", legacy <= keys, f"missing={legacy - keys}")

# --- Topical cross-check exclusion: related-article matches never vote ---
def topical_pred(label, conf, name="Cross-check: Example"):
    p = pred(label, conf, name=name)
    p["evidenceType"] = "topical_match_not_entailment"
    return p

topical = new_poll([pred("Real", 70.0, name="NewsModel"),
                    topical_pred("Fake", 99.0),
                    topical_pred("Fake", 99.0, name="Cross-check: Other")], "Fake News")
check("topical_matches_excluded_from_vote",
      topical["totalVotes"] == 1 and topical["winner"] == "Real"
      and topical.get("topicalMatchCount") == 2,
      f"totalVotes={topical['totalVotes']} winner={topical['winner']} topical={topical.get('topicalMatchCount')}")

only_topical = new_poll([topical_pred("Real", 95.0)], "Fake News")
check("only_topical_abstains",
      only_topical["abstain"] and only_topical["winner"] == "Unknown"
      and "only_topical_matches" in only_topical["abstainReasons"],
      f"reasons={only_topical['abstainReasons']}")

print()
failed = [k for k, v in results.items() if not v["pass"]]
print(f"{len(results) - len(failed)}/{len(results)} checks pass" + (f"; FAILED: {failed}" if failed else ""))
