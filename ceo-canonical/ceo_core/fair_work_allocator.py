from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any

from .models import ProjectState, Task


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(slots=True)
class AllocationReport:
    selected: list[str]
    branches: dict[str, int]
    deferred: int
    updated_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class FairWorkAllocator:
    """Value-aware dispatch with branch fairness and starvation protection."""

    KEY = "fair_work_allocator_v1"

    def _branch(self, state: ProjectState, task: Task) -> str:
        current = task
        seen: set[str] = set()
        while current.parent_id and current.parent_id in state.tasks and current.parent_id not in seen:
            seen.add(current.id)
            current = state.tasks[current.parent_id]
        return current.id

    def allocate(self, state: ProjectState, ready: list[Task], scores: dict[str, float], limit: int) -> list[Task]:
        if limit <= 0 or not ready:
            return []
        by_branch: dict[str, list[Task]] = {}
        for task in ready:
            by_branch.setdefault(self._branch(state, task), []).append(task)
        for rows in by_branch.values():
            rows.sort(key=lambda t: (-float(scores.get(t.id, 0.0)), t.created_at))

        selected: list[Task] = []
        branch_counts: dict[str, int] = {k: 0 for k in by_branch}
        # First pass: one high-value item per branch, ordered by branch-best value.
        branch_order = sorted(by_branch, key=lambda b: -float(scores.get(by_branch[b][0].id, 0.0)))
        for branch in branch_order:
            if len(selected) >= limit:
                break
            selected.append(by_branch[branch].pop(0)); branch_counts[branch] += 1
        # Remaining slots: value wins, but no branch may take more than half+1 while alternatives exist.
        cap = max(1, (limit + 1) // 2 + (1 if limit > 2 else 0))
        while len(selected) < limit:
            candidates = [(rows[0], b) for b, rows in by_branch.items() if rows and (branch_counts[b] < cap or not any(rr for bb, rr in by_branch.items() if bb != b and rr))]
            if not candidates:
                break
            task, branch = max(candidates, key=lambda x: float(scores.get(x[0].id, 0.0)))
            by_branch[branch].pop(0); selected.append(task); branch_counts[branch] += 1
        state.metadata[self.KEY] = AllocationReport([t.id for t in selected], {k:v for k,v in branch_counts.items() if v}, max(0, len(ready)-len(selected)), _now()).to_dict()
        return selected
