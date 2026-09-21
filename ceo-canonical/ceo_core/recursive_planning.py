from __future__ import annotations

from dataclasses import dataclass, asdict

from .decomposition_v3 import AdaptiveTaskDecomposer
from .models import ProjectState, Task, TaskStatus


@dataclass(slots=True)
class RecursivePlanningResult:
    inspected: int
    split_tasks: int
    new_tasks: int
    atomic_tasks: int
    max_depth_seen: int


class RecursivePlanningEngine:
    """Bounded recursive refinement until leaves are chat-sized or depth-limited."""

    def __init__(self, decomposer: AdaptiveTaskDecomposer | None = None) -> None:
        self.decomposer = decomposer or AdaptiveTaskDecomposer()

    def refine(self, state: ProjectState, max_splits: int = 12, max_depth: int | None = None) -> RecursivePlanningResult:
        depth_limit = max_depth if max_depth is not None else max(2, 2 + round(state.depth_percent / 20))
        inspected = split_tasks = new_tasks = atomic = 0
        queue = list(state.leaf_tasks)
        max_seen = 0
        while queue and split_tasks < max_splits:
            task = queue.pop(0)
            inspected += 1
            max_seen = max(max_seen, task.depth)
            if task.status in {TaskStatus.RUNNING, TaskStatus.COMPLETE, TaskStatus.SUPERSEDED}:
                continue
            # Control-plane continuity audits must remain single atomic work units.
            # Splitting them destroys the audit protocol and can strand descendants
            # in NEEDS_REVIEW without the goal_continuity_audit marker.
            if task.metadata.get("goal_continuity_audit") or task.metadata.get("control_plane_atomic"):
                task.metadata["atomic_work_unit"] = True
                task.metadata["complexity_score"] = 0.0
                atomic += 1
                continue
            assessment = self.decomposer.estimator.assess(task)
            if task.depth >= depth_limit or not assessment.too_large:
                task.metadata["atomic_work_unit"] = True
                task.metadata["complexity_score"] = assessment.score
                atomic += 1
                continue
            children = self.decomposer.split(state, task, assessment.recommended_parts)
            if children:
                split_tasks += 1; new_tasks += len(children); queue.extend(children)
        result = RecursivePlanningResult(inspected, split_tasks, new_tasks, atomic, max_seen)
        state.metadata["recursive_planning"] = asdict(result)
        return result
