from __future__ import annotations

from statistics import median
from typing import Any


def arbitrate_candidate_metrics(
    baseline: dict[str, list[float]],
    windows: dict[str, list[float]],
    mobile: dict[str, list[float]],
    directions: dict[str, str],
    *,
    max_regression_fraction: float = 0.02,
) -> dict[str, Any]:
    """Evidence-only comparison of two implementation candidates.

    It can identify a benchmark-preferred candidate when every required metric has
    evidence and no metric breaches the regression budget. It does not merge or
    promote the candidate.
    """
    metrics = sorted(set(baseline) | set(windows) | set(mobile))
    rows = []
    scores = {"windows": 0.0, "mobile": 0.0}
    admissible = {"windows": True, "mobile": True}
    for metric in metrics:
        b, w, m = baseline.get(metric) or [], windows.get(metric) or [], mobile.get(metric) or []
        if not b or not w or not m:
            rows.append({"metric": metric, "complete": False, "reason": "missing_samples"})
            admissible["windows"] = admissible["mobile"] = False
            continue
        bv, wv, mv = median(map(float, b)), median(map(float, w)), median(map(float, m))
        higher = str(directions.get(metric, "higher")).lower() != "lower"
        denom = max(abs(bv), 1e-12)
        wg = ((wv - bv) / denom) * (1 if higher else -1)
        mg = ((mv - bv) / denom) * (1 if higher else -1)
        wp = wg >= -abs(max_regression_fraction); mp = mg >= -abs(max_regression_fraction)
        admissible["windows"] &= wp; admissible["mobile"] &= mp
        scores["windows"] += wg; scores["mobile"] += mg
        rows.append({
            "metric": metric, "complete": True, "baseline_median": bv,
            "windows_median": wv, "mobile_median": mv,
            "windows_gain_fraction": round(wg, 8), "mobile_gain_fraction": round(mg, 8),
            "windows_within_budget": wp, "mobile_within_budget": mp,
        })
    preferred = None
    if metrics and all(x.get("complete") for x in rows):
        candidates = [k for k in ("windows", "mobile") if admissible[k]]
        if len(candidates) == 1:
            preferred = candidates[0]
        elif len(candidates) == 2 and abs(scores["windows"] - scores["mobile"]) > 1e-12:
            preferred = max(candidates, key=lambda k: scores[k])
    return {
        "schema_version": 1,
        "metrics": rows,
        "admissible": admissible,
        "aggregate_signed_gain": {k: round(v, 8) for k, v in scores.items()},
        "benchmark_preferred_candidate": preferred,
        "preference_is_advisory": True,
        "automatic_merge": False,
        "automatic_promotion": False,
    }
