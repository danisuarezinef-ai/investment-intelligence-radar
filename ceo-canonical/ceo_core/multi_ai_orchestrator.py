from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Iterable, Any

from .contracts import WorkerProvider
from .models import ProjectState, Task
from .provider_policy import ProviderPolicy


@dataclass(frozen=True)
class ProviderRouteCandidate:
    provider: str
    kind: str
    score: float
    historical_runs: int
    failure_rate: float
    avg_cost: float
    reason: str


@dataclass(frozen=True)
class MultiAIRoutePlan:
    selected: str | None
    fallback_order: list[str]
    candidates: list[ProviderRouteCandidate]
    second_opinion_recommended: bool
    rationale: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "selected": self.selected,
            "fallback_order": list(self.fallback_order),
            "candidates": [asdict(c) for c in self.candidates],
            "second_opinion_recommended": self.second_opinion_recommended,
            "rationale": list(self.rationale),
        }


class MultiAIOrchestrator:
    """Task-aware provider orchestration without changing human safety gates.

    The orchestrator never purchases capacity or enables a paid provider.  It only
    ranks providers that are already configured and exposed by the runtime.
    """

    HIGH_RISK_CAPABILITIES = {
        "publication", "security", "deployment", "payments", "destructive",
        "external_action", "production", "release", "legal", "medical",
    }

    def __init__(self) -> None:
        self.policy = ProviderPolicy()

    def _risk(self, task: Task) -> float:
        risk = float(task.metadata.get("risk", 0.0) or 0.0)
        caps = {str(x).lower() for x in task.required_capabilities}
        if caps & self.HIGH_RISK_CAPABILITIES:
            risk = max(risk, 0.8)
        if task.metadata.get("external_action"):
            risk = max(risk, 0.82)
        if task.metadata.get("irreversible") or task.metadata.get("destructive"):
            risk = max(risk, 0.95)
        if task.metadata.get("publication"):
            risk = max(risk, 0.9)
        return max(0.0, min(1.0, risk))

    def plan(self, state: ProjectState, task: Task, providers: Iterable[WorkerProvider]) -> MultiAIRoutePlan:
        avoid = set(task.metadata.get("avoid_providers", []) or [])
        compatible = [p for p in providers if p.supports(task) and p.name not in avoid]
        if not compatible:
            compatible = [p for p in providers if p.supports(task)]
        candidates: list[ProviderRouteCandidate] = []
        for provider in compatible:
            stats = self.policy.stats(state, provider.name)
            runs = int(stats.get("runs", 0) or 0)
            failures = int(stats.get("failures", 0) or 0)
            failure_rate = failures / max(1, runs)
            avg_cost = float(stats.get("cost", 0.0) or 0.0) / max(1, runs)
            score = float(self.policy.score(state, provider.name, task=task))
            reason_parts = []
            if runs == 0:
                if getattr(provider.kind, "value", str(provider.kind)) == "api":
                    score += 0.10
                    reason_parts.append("api cold-start preference")
                else:
                    reason_parts.append("cold-start")
            else:
                reason_parts.append("learned utility")
            # A provider with repeated failures remains available as a last resort,
            # but does not dominate merely because of a high historical quality score.
            score -= min(1.5, failure_rate * 1.2)
            if self.policy.circuit_open(state, provider.name):
                score -= 10.0
                reason_parts.append("circuit open")
            if state.priority_mode == "cost_min" and avg_cost > 0:
                reason_parts.append("cost penalized")
            candidates.append(ProviderRouteCandidate(
                provider=provider.name,
                kind=getattr(provider.kind, "value", str(provider.kind)),
                score=round(score, 5),
                historical_runs=runs,
                failure_rate=round(failure_rate, 5),
                avg_cost=round(avg_cost, 6),
                reason=", ".join(reason_parts),
            ))
        candidates.sort(key=lambda c: (c.score, c.kind == "api", -c.avg_cost), reverse=True)
        selected = candidates[0].provider if candidates else None
        fallback = [c.provider for c in candidates[1:]]
        risk = self._risk(task)
        second = bool(len(candidates) > 1 and (risk >= 0.65 or state.verification_percent >= 80))
        rationale = [f"risk={risk:.2f}", f"priority_mode={state.priority_mode}"]
        if second:
            rationale.append("independent second opinion recommended")
        if not candidates:
            rationale.append("no compatible configured provider")
        plan = MultiAIRoutePlan(selected, fallback, candidates, second, rationale)
        task.metadata["multi_ai_route_plan"] = plan.to_dict()
        state.metadata["last_multi_ai_route"] = {
            "task_id": task.id,
            "task_title": task.title,
            **plan.to_dict(),
        }
        return plan
