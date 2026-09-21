from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any

from .models import ProjectState, Task


@dataclass(frozen=True)
class ConsensusPlan:
    independent_checks: int
    adversarial_check: bool
    require_distinct_provider: bool
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ConsensusVerificationEngine:
    """Risk-adaptive cross-provider verification for important results."""

    def plan(self, state: ProjectState, task: Task, *, available_providers: int = 1) -> ConsensusPlan:
        risk = float(task.metadata.get("risk", 0.0) or 0.0)
        if task.metadata.get("external_action"):
            risk = max(risk, .8)
        if task.metadata.get("irreversible") or task.metadata.get("publication"):
            risk = max(risk, .95)
        q = task.quality_score if task.quality_score is not None else 0.7
        verification = int(state.verification_percent)
        checks = 0
        if verification >= 60 or q < .65 or risk >= .6:
            checks = 1
        if verification >= 85 or q < .5 or risk >= .82:
            checks = 2
        if verification >= 97 and risk >= .9:
            checks = 3
        # There is no value in requesting more distinct-provider checks than there
        # are configured alternatives; same-provider checks may still be created by
        # the existing layered verifier, but do not count as independent consensus.
        distinct = available_providers > 1
        if distinct:
            checks = min(checks, max(1, available_providers - 1))
        adversarial = bool(verification >= 92 or risk >= .85)
        reason = f"verification={verification}; risk={risk:.2f}; quality={q:.2f}"
        return ConsensusPlan(checks, adversarial, distinct, reason)

    def adjudicate(self, original_provider: str | None, reviews: list[dict[str, Any]]) -> dict[str, Any]:
        normalized = []
        for row in reviews:
            provider = str(row.get("provider") or "unknown")
            verdict = str(row.get("verdict") or "uncertain").lower()
            confidence = max(0.0, min(1.0, float(row.get("confidence", .5) or .5)))
            if verdict not in {"pass", "fail", "uncertain"}:
                verdict = "uncertain"
            normalized.append({"provider": provider, "verdict": verdict, "confidence": confidence})
        independent = [r for r in normalized if not original_provider or r["provider"] != original_provider]
        votes = independent or normalized
        support = sum(r["confidence"] for r in votes if r["verdict"] == "pass")
        oppose = sum(r["confidence"] for r in votes if r["verdict"] == "fail")
        uncertain = sum(r["confidence"] for r in votes if r["verdict"] == "uncertain")
        if not votes:
            verdict = "insufficient"
        elif support > oppose * 1.25 and support >= uncertain:
            verdict = "pass"
        elif oppose > support * 1.25 and oppose >= uncertain:
            verdict = "fail"
        else:
            verdict = "disputed"
        return {
            "verdict": verdict,
            "independent_reviews": len(independent),
            "providers": sorted({r["provider"] for r in independent}),
            "support_weight": round(support, 4),
            "oppose_weight": round(oppose, 4),
            "uncertain_weight": round(uncertain, 4),
            "reviews": normalized,
        }
