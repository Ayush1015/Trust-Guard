# Historical function used solely to reproduce the fixed confidence defect.
def model_poll(predictions: list[dict[str, Any]], task: str) -> dict[str, Any]:
    """Aggregate compatible predictions into an inspectable ensemble result.

    A prediction contributes ``confidence * weight`` to its label.  This means
    model confidence and explicit voter weights affect both the winner and the
    reported confidence instead of being used only as a tie-breaker.
    """
    valid: list[dict[str, Any]] = []

    for prediction in predictions or []:
        if not prediction:
            continue
        if prediction.get("status") != "participated":
            continue
        label = prediction.get("label")
        if label in {None, "", "Unknown"}:
            continue

        try:
            confidence = clamp01(prediction.get("confidence"), 0.5)
            weight = max(0.1, float(prediction.get("weight", 1.0)))
        except (TypeError, ValueError):
            logger.warning("[POLL] Ignoring malformed prediction: %r", prediction)
            continue

        normalized = dict(prediction)
        normalized["confidence"] = round(confidence * 100, 2)
        normalized["weight"] = weight
        valid.append(normalized)

    if not valid:
        return {
            "winner": "Unknown",
            "votes": {},
            "weightedVotes": {},
            "weightedSharePercent": {},
            "totalVotes": 0,
            "winningVotes": 0,
            "confidence": 0,
            "voteRatioConfidence": 0,
            "weightedConfidence": 0,
            "margin": 0,
            "runnerUp": None,
            "isUnanimous": False,
            "isTie": False,
            "models": [],
            "task": task,
        }

    votes = Counter(p["label"] for p in valid)
    weighted: dict[str, float] = {}

    for prediction in valid:
        label = prediction["label"]
        confidence = clamp01(prediction.get("confidence"), 0.5)
        weight = max(0.1, float(prediction.get("weight", 1.0)))
        weighted[label] = weighted.get(label, 0.0) + confidence * weight

    # Weighted score is the primary decision signal.
    ranked = sorted(
        weighted.items(),
        key=lambda item: (item[1], votes.get(item[0], 0)),
        reverse=True,
    )
    winner = ranked[0][0]

    winning_votes = votes[winner]
    vote_ratio_confidence = winning_votes / len(valid)
    total_weighted = sum(weighted.values())

    weighted_confidence = (
        weighted[winner] / total_weighted if total_weighted > 0 else 0.0
    )

    runner_up = None
    margin = winning_votes
    if len(ranked) > 1:
        runner_label, runner_score = ranked[1]
        runner_votes = votes[runner_label]
        runner_up = {
            "label": runner_label,
            "votes": runner_votes,
            "weightedScore": round(runner_score, 4),
            "weightedSharePercent": round(
                (runner_score / total_weighted) * 100 if total_weighted else 0.0,
                2,
            ),
        }
        margin = winning_votes - runner_votes

    weighted_share_percent = {
        label: round((score / total_weighted) * 100 if total_weighted else 0.0, 2)
        for label, score in weighted.items()
    }

    return {
        "winner": winner,
        "votes": dict(votes),
        "weightedVotes": {label: round(score, 4) for label, score in weighted.items()},
        "weightedSharePercent": weighted_share_percent,
        "totalVotes": len(valid),
        "winningVotes": winning_votes,
        "confidence": round(weighted_confidence * 100, 2),
        "voteRatioConfidence": round(vote_ratio_confidence * 100, 2),
        "weightedConfidence": round(weighted_confidence * 100, 2),
        "margin": margin,
        "runnerUp": runner_up,
        "isUnanimous": len(votes) == 1,
        "isTie": len(ranked) > 1 and weighted[ranked[0][0]] == weighted[ranked[1][0]],
        "models": valid,
        "task": task,
      }
