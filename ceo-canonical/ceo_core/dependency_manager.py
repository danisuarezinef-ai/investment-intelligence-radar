from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

from .models import ProjectState, Task, TaskStatus
from .blocked_safe_state_v1 import preserve_blocked_safe


_DONE = {TaskStatus.COMPLETE, TaskStatus.PARTIAL_COMPLETE, TaskStatus.COMPLETE_WITH_UNCERTAINTY, TaskStatus.SUPERSEDED}
_ACTIVE_MUTABLE = {TaskStatus.WAITING, TaskStatus.READY, TaskStatus.BLOCKED, TaskStatus.RETRY}


@dataclass(slots=True)
class DependencyReport:
    missing: int = 0
    failed_hard: int = 0
    soft_edges_removed: int = 0
    any_of_satisfied: int = 0
    unblocked: int = 0
    cycles: int = 0

    def to_dict(self) -> dict[str, int]:
        return asdict(self)


class DependencyManager:
    """Conservative branch-local dependency reconciliation.

    Hard dependencies are never silently deleted. Soft edges can be removed when they
    are the cause of a cycle or point to a failed/missing task. Unrelated branches keep
    running because only directly affected tasks are blocked.
    """

    def reconcile(self, state: ProjectState) -> DependencyReport:
        report = DependencyReport()
        cycle_edges = self._cycle_edges(state)
        report.cycles = len(cycle_edges)

        for task in state.leaf_tasks:
            if preserve_blocked_safe(task, source="dependency_manager"):
                continue
            if task.status not in _ACTIVE_MUTABLE:
                continue
            soft = set(str(x) for x in (task.metadata.get("soft_dependency_ids") or []))
            original = list(task.dependencies)
            kept: list[str] = []
            hard_blockers: list[dict[str, Any]] = []

            for dep in original:
                if dep not in state.tasks:
                    if dep in soft:
                        report.soft_edges_removed += 1
                        continue
                    report.missing += 1
                    hard_blockers.append({"dependency": dep, "reason": "missing"})
                    kept.append(dep)
                    continue
                dep_task = state.tasks[dep]
                if (task.id, dep) in cycle_edges and dep in soft:
                    report.soft_edges_removed += 1
                    continue
                if dep_task.status == TaskStatus.FAILED:
                    if dep in soft or task.metadata.get("dependency_policy") == "best_effort":
                        report.soft_edges_removed += 1
                        continue
                    report.failed_hard += 1
                    hard_blockers.append({"dependency": dep, "reason": "failed"})
                kept.append(dep)

            if kept != original:
                task.dependencies = kept

            any_groups = task.metadata.get("dependency_any_of") or []
            any_satisfied = True
            if any_groups:
                any_satisfied = False
                for group in any_groups:
                    ids = [str(x) for x in (group if isinstance(group, list) else [group])]
                    if any(dep in state.tasks and state.tasks[dep].status in _DONE for dep in ids):
                        any_satisfied = True
                        report.any_of_satisfied += 1
                        break

            hard_done = all(dep in state.tasks and state.tasks[dep].status in _DONE for dep in task.dependencies)
            retry_after = float(task.metadata.get("retry_after_ts", 0) or 0)
            ready = hard_done and any_satisfied and retry_after <= datetime.now(timezone.utc).timestamp() and not hard_blockers and not task.metadata.get("paused")
            if ready and task.status in {TaskStatus.WAITING, TaskStatus.BLOCKED, TaskStatus.RETRY}:
                task.status = TaskStatus.READY
                task.metadata.pop("dependency_blockers", None)
                report.unblocked += 1
            elif not ready and task.status in {TaskStatus.WAITING, TaskStatus.READY, TaskStatus.BLOCKED, TaskStatus.RETRY}:
                task.status = TaskStatus.BLOCKED
                blockers = list(hard_blockers)
                if not any_satisfied:
                    blockers.append({"reason": "any_of_unsatisfied", "groups": any_groups})
                for dep in task.dependencies:
                    if dep in state.tasks and state.tasks[dep].status not in _DONE:
                        blockers.append({"dependency": dep, "reason": state.tasks[dep].status.value})
                task.metadata["dependency_blockers"] = blockers[:20]

        state.metadata["dependency_health"] = {**report.to_dict(), "ts": datetime.now(timezone.utc).isoformat()}
        return report

    def _cycle_edges(self, state: ProjectState) -> set[tuple[str, str]]:
        edges: set[tuple[str, str]] = set()
        visiting: set[str] = set()
        visited: set[str] = set()

        def dfs(tid: str, path: list[str]) -> None:
            if tid in visited or tid not in state.tasks:
                return
            if tid in visiting:
                return
            visiting.add(tid)
            path.append(tid)
            for dep in state.tasks[tid].dependencies:
                if dep not in state.tasks:
                    continue
                if dep in visiting:
                    try:
                        idx = path.index(dep)
                        cycle = path[idx:] + [dep]
                        for a, b in zip(cycle, cycle[1:]):
                            edges.add((a, b))
                    except ValueError:
                        edges.add((tid, dep))
                else:
                    dfs(dep, path)
            path.pop()
            visiting.remove(tid)
            visited.add(tid)

        for tid in list(state.tasks):
            dfs(tid, [])
        return edges
