from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

from .graph import TaskGraph
from .models import ProjectState, Task


@dataclass(slots=True)
class ValueScore:
    total: float
    urgency: float
    downstream: float
    critical_path: float
    information: float
    success_probability: float
    quality_gap: float
    cost_penalty: float
    time_penalty: float
    deadline_pressure: float
    mode_adjustment: float

    def to_dict(self) -> dict[str, float]:
        return {k: round(float(v), 4) for k, v in asdict(self).items()}


class ValuePrioritizer:
    """Explainable value/cost prioritization for executable work.

    Batch scoring deliberately precomputes graph features once so projects with
    thousands of ready work units do not incur one full graph walk per task.
    """

    def _components(self, state: ProjectState, task: Task, *, downstream_n: int, critical: bool) -> ValueScore:
        urgency = (int(task.priority) / 100.0) * 2.6 + (int(state.urgency) / 100.0) * 0.9
        downstream = min(2.5, downstream_n * 0.18)
        critical_path = 1.8 if critical else 0.0
        uncertainty = 1.0 - float(task.confidence if task.confidence is not None else task.metadata.get("confidence_prior", 0.5))
        information = max(0.0, min(1.0, float(task.metadata.get("information_value", uncertainty)))) * 1.25
        success = max(0.0, min(1.0, float(task.metadata.get("predicted_success_probability", 0.65)))) * 0.9
        quality_gap = max(0.0, 0.75 - float(task.quality_score or 0.75)) * (1.0 if task.metadata.get("verification_task") or task.metadata.get("self_correction_replacement_of") else 0.35)
        cost_penalty = min(2.2, max(0.0, float(task.cost_estimate or 0.0)) * 2.0)
        time_penalty = min(1.8, max(0.0, float(task.estimated_seconds or 0.0)) / 180.0)
        deadline_pressure = max(0.0, min(1.0, float((state.metadata.get("deadline_intelligence") or {}).get("pressure", 0.0) or 0.0))) * 1.5
        mode = str(state.priority_mode or "balanced")
        mode_adjustment = 0.0
        if mode == "cost_min":
            mode_adjustment -= cost_penalty * 0.75
        elif mode in {"speed", "fast"}:
            mode_adjustment -= time_penalty * 0.65
        elif mode in {"quality", "high_quality"}:
            mode_adjustment += quality_gap * 0.9 + information * 0.25
        if task.metadata.get("explicit_human_gate"):
            mode_adjustment -= 100.0

        total = urgency + downstream + critical_path + information + success + quality_gap + deadline_pressure + mode_adjustment - cost_penalty - time_penalty
        return ValueScore(total, urgency, downstream, critical_path, information, success, quality_gap, cost_penalty, time_penalty, deadline_pressure, mode_adjustment)

    def explain(self, state: ProjectState, task: Task, graph: TaskGraph) -> ValueScore:
        critical = task.id in set(graph.remaining_critical_path(state).get("task_ids", []))
        downstream_n = graph.downstream_count(state, task.id)
        return self._components(state, task, downstream_n=downstream_n, critical=critical)

    def score(self, state: ProjectState, task: Task, graph: TaskGraph) -> float:
        value = self.explain(state, task, graph)
        task.metadata["value_priority"] = value.to_dict()
        return value.total

    def score_many(self, state: ProjectState, tasks: list[Task], graph: TaskGraph) -> dict[str, float]:
        reverse_counts = {tid: 0 for tid in state.tasks}
        for row in state.tasks.values():
            for dep in row.dependencies:
                if dep in reverse_counts:
                    reverse_counts[dep] += 1
        critical = set(graph.remaining_critical_path(state).get("task_ids", []))
        scores: dict[str, float] = {}
        for task in tasks:
            value = self._components(state, task, downstream_n=reverse_counts.get(task.id, 0), critical=task.id in critical)
            task.metadata["value_priority"] = value.to_dict()
            scores[task.id] = value.total
        state.metadata["value_prioritization_last"] = {
            "candidates": len(tasks),
            "critical_candidates": sum(1 for t in tasks if t.id in critical),
            "mode": state.priority_mode,
        }
        return scores

    def ranked(self, state: ProjectState, tasks: list[Task], graph: TaskGraph) -> list[Task]:
        scores = self.score_many(state, tasks, graph)
        return sorted(tasks, key=lambda t: (-scores.get(t.id, float("-inf")), t.created_at))
