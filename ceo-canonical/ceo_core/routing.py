from __future__ import annotations

from collections import defaultdict

from ceo_core.contracts import WorkerProvider, WorkerRouter
from ceo_core.models import ProjectState, Task
from ceo_core.provider_policy import ProviderPolicy
from ceo_core.provider_intelligence import ProviderIntelligenceEngine
from ceo_core.release_candidate_v1 import ModelPortfolioManager, ProviderOutageSimulator
from ceo_core.multi_ai_orchestrator import MultiAIOrchestrator


class MultiProviderRouter(WorkerRouter):
    """Selects among API/browser/local workers without scheduler coupling."""

    def __init__(self, providers: list[WorkerProvider], default_provider: str | None = None) -> None:
        if not providers:
            raise ValueError("At least one provider is required")
        self.providers = providers
        self.by_name = {p.name: p for p in providers}
        self.default_provider = default_provider or providers[0].name
        self._rr: dict[str, int] = defaultdict(int)
        self.policy = ProviderPolicy()
        self.intelligence = ProviderIntelligenceEngine()
        self.model_portfolio = ModelPortfolioManager()
        self.outages = ProviderOutageSimulator()
        self.multi_ai = MultiAIOrchestrator()

    def select(self, task: Task, state: ProjectState) -> WorkerProvider:
        preferred = task.metadata.get("preferred_provider")
        if preferred and preferred in self.by_name and self.by_name[preferred].supports(task):
            return self.by_name[preferred]

        preferred_kind = task.metadata.get("preferred_kind")
        candidates = [p for p in self.providers if p.supports(task)]
        if preferred_kind:
            kind_candidates = [p for p in candidates if p.kind.value == preferred_kind]
            if kind_candidates:
                candidates = kind_candidates
        if not candidates:
            raise RuntimeError(f"No provider can execute task '{task.title}'")
        avoid = set(task.metadata.get("avoid_providers", []))
        alternative = [p for p in candidates if p.name not in avoid]
        if alternative:
            candidates = alternative

        # Roadmap 81-84: hard outages are never selected when an alternative exists;
        # empirically degraded providers are deprioritized without erasing their history.
        non_outage = [p for p in candidates if not self.outages.unavailable(state, p.name)]
        if non_outage:
            candidates = non_outage
        non_degraded = [p for p in candidates if self.model_portfolio.profile(state, p.name).get("status") != "degraded"]
        if non_degraded:
            candidates = non_degraded

        # Exclude temporarily unhealthy providers when alternatives exist, then favor
        # observed quality/success/latency. This is also the automatic fallback path.
        healthy = [p for p in candidates if not self.policy.circuit_open(state, p.name)]
        if healthy:
            candidates = healthy
        route_plan = self.multi_ai.plan(state, task, candidates)
        route_scores = {row.provider: row.score for row in route_plan.candidates}
        scored = {p.name: route_scores.get(p.name, self.policy.score(state, p.name, task=task)) for p in candidates}

        # API-first cold start: real API providers are the primary autonomous path. Once
        # task-specific evidence exists, learned quality/cost/latency scores take over.
        has_evidence = any(int(self.policy.task_stats(state, p.name, self.policy.task_type(task)).get("runs", 0)) > 0 for p in candidates)
        if not has_evidence and not preferred_kind:
            for p in candidates:
                if p.kind.value == "api":
                    scored[p.name] += 0.12
                elif p.kind.value == "browser":
                    scored[p.name] -= 0.03

        # Feed the same score ordering into champion/challenger selection while preserving
        # the engine's exploration cadence. On a cold start we explicitly prefer the best
        # API candidate rather than relying on provider-name tie breaking.
        decision = self.intelligence.choose(state, task, [p.name for p in candidates])
        ranked = sorted(candidates, key=lambda p: (scored[p.name], p.kind.value == "api"), reverse=True)
        champion = ranked[0].name if ranked else decision.champion
        challenger = ranked[1].name if len(ranked) > 1 else None
        explore = bool(decision.explore and challenger)
        selected_name = challenger if explore else champion
        task.metadata["provider_routing"] = {
            "champion": champion,
            "challenger": challenger,
            "explore": explore,
            "selected": selected_name,
            "ranking": [
                {"provider": p.name, "kind": p.kind.value, "score": round(scored[p.name], 4)}
                for p in ranked
            ],
            "reason": "challenger_exploration" if explore else ("api_first_cold_start" if not has_evidence and self.by_name[selected_name].kind.value == "api" else "learned_utility"),
            "fallback_order": list(route_plan.fallback_order),
            "second_opinion_recommended": bool(route_plan.second_opinion_recommended),
        }
        if selected_name and selected_name in self.by_name:
            return self.by_name[selected_name]
        best_score = max(scored.values())
        best = [p for p in candidates if scored[p.name] == best_score]
        key = task.metadata.get("preferred_kind") or "general"
        idx = self._rr[key] % len(best); self._rr[key] += 1
        return best[idx]
