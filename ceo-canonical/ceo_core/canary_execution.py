from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any

from .models import ProjectState


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(slots=True)
class CanaryVerdict:
    candidate_id: str
    eligible_for_human_promotion: bool
    reason: str
    baseline_score: float
    candidate_score: float
    samples: int
    at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class CanaryExecutionManager:
    KEY = "canary_execution_v1"

    def plan(self, state: ProjectState, candidate_id: str, *, side_effect_free: bool, sample_percent: int = 5) -> dict[str, Any]:
        pct = max(1, min(int(sample_percent), 25))
        mode = "shadow" if not side_effect_free else "canary"
        row = {"candidate_id": candidate_id, "mode": mode, "sample_percent": pct, "side_effect_free": bool(side_effect_free), "automatic_promotion": False, "created_at": _now()}
        state.metadata.setdefault(self.KEY, {}).setdefault("plans", {})[candidate_id] = row
        return row

    def evaluate(self, state: ProjectState, candidate_id: str, *, baseline: list[float], candidate: list[float], max_regression: float = 0.02) -> CanaryVerdict:
        if not baseline or not candidate or len(candidate) != len(baseline):
            verdict = CanaryVerdict(candidate_id, False, "insufficient_or_unpaired_samples", 0.0, 0.0, min(len(baseline), len(candidate)), _now())
        else:
            b = sum(baseline) / len(baseline); c = sum(candidate) / len(candidate)
            eligible = c + float(max_regression) >= b
            verdict = CanaryVerdict(candidate_id, eligible, "eligible_for_human_review" if eligible else "regression_budget_exceeded", round(b, 6), round(c, 6), len(candidate), _now())
        root = state.metadata.setdefault(self.KEY, {})
        root.setdefault("verdicts", {})[candidate_id] = verdict.to_dict()
        root["automatic_promotion"] = False
        return verdict
