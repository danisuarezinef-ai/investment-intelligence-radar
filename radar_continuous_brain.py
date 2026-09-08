"""Continuous Brain governance for Radar.

Turns mature forward evidence into conservative, versioned learning proposals.
Historical evidence can generate challengers, but only live-forward evidence may
promote an operational brain. Real trading is intentionally disabled.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import sqrt
from typing import Iterable, Mapping, Sequence

REAL_TRADING = False
MIN_LIVE_OBSERVATIONS = 40
MIN_LIVE_GAIN = 0.005
MAX_REGRESSION = 0.01
MAX_COMPLEXITY_DELTA = 0.10

@dataclass(frozen=True)
class EvidenceScore:
    n: int
    objective: float
    brier: float | None = None
    drawdown: float | None = None

@dataclass(frozen=True)
class BrainCandidate:
    version: str
    parent_version: str
    historical: EvidenceScore | None
    live: EvidenceScore | None
    baseline_live: EvidenceScore | None
    complexity_delta: float = 0.0
    provenance_ok: bool = False
    immutable_forward: bool = False


def live_gain(candidate: BrainCandidate) -> float | None:
    if not candidate.live or not candidate.baseline_live:
        return None
    return candidate.live.objective - candidate.baseline_live.objective


def promotion_gate(candidate: BrainCandidate) -> dict:
    """Conservative operational-promotion gate.

    Historical evidence is deliberately absent from the acceptance rule. It may
    create/qualify a shadow challenger, never an operational champion.
    """
    reasons: list[str] = []
    if not candidate.provenance_ok:
        reasons.append("provenance_not_verified")
    if not candidate.immutable_forward:
        reasons.append("forward_evidence_not_immutable")
    if not candidate.live or candidate.live.n < MIN_LIVE_OBSERVATIONS:
        reasons.append("insufficient_live_observations")
    gain = live_gain(candidate)
    if gain is None or gain < MIN_LIVE_GAIN:
        reasons.append("insufficient_live_gain")
    if candidate.complexity_delta > MAX_COMPLEXITY_DELTA:
        reasons.append("complexity_not_earned")
    if candidate.live and candidate.baseline_live:
        if candidate.live.drawdown is not None and candidate.baseline_live.drawdown is not None:
            # drawdown is expected as a non-positive return; more negative is worse.
            if candidate.live.drawdown < candidate.baseline_live.drawdown - MAX_REGRESSION:
                reasons.append("drawdown_regression")
        if candidate.live.brier is not None and candidate.baseline_live.brier is not None:
            if candidate.live.brier > candidate.baseline_live.brier + MAX_REGRESSION:
                reasons.append("calibration_regression")
    return {
        "accepted": not reasons,
        "reasons": reasons,
        "candidate": candidate.version,
        "parent": candidate.parent_version,
        "live_gain": gain,
        "real_trading": False,
    }


def transfer_weight(historical_gain: float, live_gain_value: float, historical_n: int, live_n: int) -> float:
    """How much historical success should influence future search.

    It grows only when historical and live signs agree and is bounded below 1;
    disagreement drives historical transfer toward zero.
    """
    if historical_n <= 0 or live_n <= 0 or historical_gain * live_gain_value <= 0:
        return 0.0
    evidence = min(1.0, sqrt(live_n / max(40.0, historical_n)))
    agreement = min(1.0, abs(live_gain_value) / max(abs(historical_gain), 1e-9))
    return min(0.75, evidence * agreement)


def family_score(live_objectives: Sequence[float], complexity: float, instability: float) -> float:
    """Meta-learning score: reward durable live value, penalize fragility/complexity."""
    if not live_objectives:
        return float("-inf")
    mean = sum(live_objectives) / len(live_objectives)
    return mean - max(0.0, instability) - 0.05 * max(0.0, complexity)


def retire_component(incremental_live_values: Iterable[float], min_samples: int = 3, min_mean_gain: float = 0.001) -> bool:
    """Retire complexity only after repeated mature live comparisons."""
    values = list(incremental_live_values)
    if len(values) < min_samples:
        return False
    return (sum(values) / len(values)) < min_mean_gain


def brain_state(champion: str, candidates: Sequence[BrainCandidate]) -> dict:
    evaluated = [promotion_gate(c) for c in candidates]
    return {
        "champion": champion,
        "candidates": evaluated,
        "live_ready": any(x["accepted"] for x in evaluated),
        "real_trading": False,
    }
