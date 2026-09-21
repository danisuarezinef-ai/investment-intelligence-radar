from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .models import Decision, ProjectState


class DecisionClass(str, Enum):
    TRIVIAL = "trivial"
    ROUTINE = "routine"
    IMPORTANT = "important"
    CRITICAL = "critical"


@dataclass(slots=True)
class DecisionAssessment:
    classification: DecisionClass
    auto_resolve: bool
    timeout_seconds: int
    score: float


class AutonomyEngine:
    """Classifies decisions by impact/reversibility/cost and user confidence."""

    def assess(self, state: ProjectState, decision: Decision) -> DecisionAssessment:
        m = decision.metadata
        irreversibility = float(m.get("irreversibility", 0.0))
        external = 1.0 if m.get("external_effect") else 0.0
        cost = min(1.0, float(m.get("cost", 0.0)) / max(1.0, float(state.budget_limit or 100.0)))
        impact = float(m.get("project_impact", .35))
        confidence = float(decision.confidence or 0.0)
        risk = min(1.0, irreversibility * .35 + external * .25 + cost * .15 + impact * .35)
        if risk >= .75:
            cls = DecisionClass.CRITICAL
        elif risk >= .48:
            cls = DecisionClass.IMPORTANT
        elif risk >= .18:
            cls = DecisionClass.ROUTINE
        else:
            cls = DecisionClass.TRIVIAL
        threshold = {DecisionClass.TRIVIAL: .45, DecisionClass.ROUTINE: .68, DecisionClass.IMPORTANT: .90, DecisionClass.CRITICAL: 1.01}[cls]
        # Operator autonomy profiles may lower/raise thresholds for reversible choices.
        # Critical/irreversible actions remain non-automatic regardless of profile.
        delta = float(state.metadata.get("autonomy_threshold_delta", 0.0) or 0.0)
        if cls != DecisionClass.CRITICAL:
            threshold = max(.20, min(.99, threshold + delta))
        auto = state.autonomy_enabled and confidence >= threshold and not (cls == DecisionClass.CRITICAL)
        timeout = {DecisionClass.TRIVIAL: 15, DecisionClass.ROUTINE: 60, DecisionClass.IMPORTANT: 180, DecisionClass.CRITICAL: 0}[cls]
        return DecisionAssessment(cls, auto, timeout, round(1 - risk, 4))

    def annotate(self, state: ProjectState, decision: Decision) -> DecisionAssessment:
        assessment = self.assess(state, decision)
        decision.metadata["autonomy_class"] = assessment.classification.value
        decision.metadata["auto_resolve_allowed"] = assessment.auto_resolve
        if assessment.timeout_seconds and decision.timeout_seconds <= 0:
            decision.timeout_seconds = assessment.timeout_seconds
        return assessment
