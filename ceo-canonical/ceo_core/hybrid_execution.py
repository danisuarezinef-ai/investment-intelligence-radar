from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from .models import ProjectState, TaskStatus


@dataclass(slots=True)
class HybridExecutionPlan:
    total_target: int
    by_kind: dict[str, int]
    queued_by_kind: dict[str, int]


class HybridExecutionEngine:
    """Plans one shared execution budget across API/browser/local/file worker classes."""

    KINDS = ("api", "browser", "local", "file")

    def plan(self, state: ProjectState, total_target: int, limits: dict[str, int | float]) -> HybridExecutionPlan:
        queued = Counter(str(t.metadata.get("preferred_kind", "api")) for t in state.leaf_tasks if t.status == TaskStatus.READY)
        alloc: dict[str, int] = {}
        remaining = total_target
        for kind in self.KINDS:
            cap = int(limits.get(f"{kind}_workers", total_target))
            wanted = min(cap, queued.get(kind, 0))
            alloc[kind] = wanted
            remaining -= wanted
        if remaining > 0:
            for kind in sorted(self.KINDS, key=lambda k: queued.get(k, 0) - alloc.get(k, 0), reverse=True):
                cap = int(limits.get(f"{kind}_workers", total_target))
                add = min(remaining, max(0, cap - alloc[kind]), max(0, queued.get(kind, 0) - alloc[kind]))
                alloc[kind] += add
                remaining -= add
                if remaining <= 0:
                    break
        return HybridExecutionPlan(total_target, alloc, {k: queued.get(k, 0) for k in self.KINDS})
