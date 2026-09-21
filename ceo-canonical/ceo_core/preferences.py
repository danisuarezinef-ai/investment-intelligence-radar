from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any

from .models import ProjectState


@dataclass(slots=True)
class PreferencePrediction:
    option: str | None
    confidence: float
    evidence_count: int


class PreferenceLearningEngine:
    """Learns soft user preferences; never converts them into irreversible hard rules."""

    def predict(self, state: ProjectState, situation: str, options: list[str]) -> PreferencePrediction:
        history = list(state.metadata.get("decision_history", []))
        weights: dict[str, float] = defaultdict(float)
        evidence = 0
        for row in history:
            past = str(row.get("title") or row.get("situation") or row.get("id") or "")
            similarity = SequenceMatcher(None, situation.lower(), past.lower()).ratio() if past else 0.0
            if similarity < .35:
                continue
            selected = str(row.get("selected") or "")
            match = next((o for o in options if o.lower() == selected.lower()), None)
            if match:
                outcome = str(row.get("outcome") or "")
                outcome_weight = 1.25 if outcome in {"success", "good"} else .5 if outcome in {"failure", "bad"} else 1.0
                weights[match] += similarity * outcome_weight
                evidence += 1
        if not weights:
            return PreferencePrediction(None, 0.0, 0)
        best = max(weights, key=weights.get)
        total = sum(weights.values())
        return PreferencePrediction(best, round(weights[best] / max(.001, total) * min(1.0, evidence / 5), 4), evidence)

    def annotate_recommendation(self, state: ProjectState, situation: str, options: list[str], recommendation: str | None) -> tuple[str | None, float]:
        pred = self.predict(state, situation, options)
        if pred.option and pred.confidence >= .7:
            return pred.option, pred.confidence
        return recommendation, pred.confidence
