from __future__ import annotations

import random
from dataclasses import dataclass, asdict
from statistics import median

from .graph import TaskGraph
from .models import ProjectState, TaskStatus
from .resource_governor import ResourceGovernor


@dataclass(slots=True)
class EtaEstimate:
    median_seconds: float
    p10_seconds: float
    p90_seconds: float
    confidence: float
    samples: int


class MonteCarloETAEngine:
    """Dependency-aware stochastic ETA using observed task duration dispersion."""

    TERMINAL = {TaskStatus.COMPLETE, TaskStatus.PARTIAL_COMPLETE, TaskStatus.COMPLETE_WITH_UNCERTAINTY, TaskStatus.SUPERSEDED}

    def __init__(self, graph: TaskGraph | None = None, governor: ResourceGovernor | None = None, seed: int = 7) -> None:
        self.graph = graph or TaskGraph()
        self.governor = governor or ResourceGovernor()
        self.random = random.Random(seed)

    def estimate(self, state: ProjectState, power_percent: int | None = None, simulations: int = 300) -> EtaEstimate:
        power = state.power_percent if power_percent is None else power_percent
        workers = max(1, self.governor.target_concurrency(power))
        remaining = [t for t in state.leaf_tasks if t.status not in self.TERMINAL]
        observed = [float(t.actual_seconds) for t in state.leaf_tasks if t.actual_seconds and t.actual_seconds > 0]
        estimates = [max(.02, float(t.actual_seconds or t.estimated_seconds or 1.0)) for t in remaining]
        typical = median(observed) if observed else median(estimates or [1.0])
        spread = max(.12, min(1.2, (max(observed) / max(.05, typical) - 1) if len(observed) >= 3 else .35))
        critical = float(self.graph.remaining_critical_path(state)["seconds"])
        # O(tasks + simulations), not O(tasks * simulations). Heterogeneous task estimates
        # are aggregated once; simulation models systemic duration/retry uncertainty.
        base_work = sum(estimates)
        failure_probs = [float(t.metadata.get("historical_failure_rate", .03)) for t in remaining]
        mean_failure = sum(failure_probs) / len(failure_probs) if failure_probs else .03
        outcomes: list[float] = []
        for _ in range(max(20, simulations)):
            systemic = self.random.lognormvariate(-.5 * (spread * .22) ** 2, spread * .22)
            retry_uplift = 1.0 + max(0.0, self.random.gauss(mean_failure, max(.01, mean_failure * .35)))
            efficiency = max(.45, .90 - min(.35, workers / 1200))
            outcomes.append(max(critical, (base_work * systemic * retry_uplift) / max(1.0, workers * efficiency)))
        outcomes.sort()
        p10 = outcomes[int(len(outcomes) * .10)]
        med = outcomes[len(outcomes) // 2]
        p90 = outcomes[min(len(outcomes) - 1, int(len(outcomes) * .90))]
        confidence = min(.95, .35 + len(observed) / 100)
        result = EtaEstimate(round(med, 2), round(p10, 2), round(p90, 2), round(confidence, 3), len(outcomes))
        state.metadata.setdefault("eta_v2", {})[str(power)] = asdict(result)
        return result

    def scenarios(self, state: ProjectState, powers=(20, 40, 60, 80, 100)) -> dict[str, dict]:
        return {str(p): asdict(self.estimate(state, p, simulations=120)) for p in powers}
