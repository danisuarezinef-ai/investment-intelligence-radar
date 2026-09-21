from __future__ import annotations

from dataclasses import dataclass

from .models import ProjectState, Task
from .provider_policy import ProviderPolicy


@dataclass(slots=True)
class ProviderDecision:
    champion: str | None
    challenger: str | None
    champion_score: float
    challenger_score: float
    explore: bool


class ProviderIntelligenceEngine:
    """Champion/challenger selection based on task-specific utility and exploration budget."""

    def __init__(self) -> None:
        self.policy = ProviderPolicy()

    def choose(self, state: ProjectState, task: Task, candidates: list[str]) -> ProviderDecision:
        if not candidates:
            return ProviderDecision(None, None, 0.0, 0.0, False)
        scored = sorted(((self.policy.score(state, p, task), p) for p in candidates), reverse=True)
        champion_score, champion = scored[0]
        challenger_score, challenger = scored[1] if len(scored) > 1 else (champion_score, None)
        sequence = int(state.metadata.get("provider_route_sequence", 0)) + 1
        state.metadata["provider_route_sequence"] = sequence
        fraction = self.policy.challenger_fraction(state)
        cadence = max(1, round(1 / max(.001, fraction)))
        explore = challenger is not None and sequence % cadence == 0
        return ProviderDecision(champion, challenger, round(champion_score, 4), round(challenger_score, 4), explore)

    def promote_if_warranted(self, state: ProjectState, task_type: str, champion: str, challenger: str, min_runs: int = 5, margin: float = .08) -> bool:
        cs = self.policy.task_stats(state, champion, task_type)
        xs = self.policy.task_stats(state, challenger, task_type)
        if int(xs.get("runs", 0)) < min_runs:
            return False
        promoted = self.policy.utility(state, challenger, task_type) > self.policy.utility(state, champion, task_type) + margin
        if promoted:
            state.metadata.setdefault("provider_promotions", []).append({"task_type": task_type, "from": champion, "to": challenger})
        return promoted
