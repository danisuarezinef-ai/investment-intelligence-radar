from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .continuity_policy import protected_human_gate
from .models import ProjectState, TaskStatus
from .blocked_safe_state_v1 import preserve_blocked_safe
from .task_roles_v2 import is_internal


_DONE = {TaskStatus.COMPLETE, TaskStatus.PARTIAL_COMPLETE, TaskStatus.COMPLETE_WITH_UNCERTAINTY, TaskStatus.SUPERSEDED}


@dataclass(slots=True)
class QueueRebuildReport:
    internal_review_recovered: int
    orphan_running_requeued: int
    dependencies_unblocked: int
    duplicate_roots_removed: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class QueueConsistencyRebuilderV1:
    KEY = "queue_consistency_rebuilder_v1"

    def rebuild(self, state: ProjectState, *, active_task_ids: set[str] | None = None) -> QueueRebuildReport:
        active = set(active_task_ids or set())
        review = orphan = deps = roots = 0
        for task in state.leaf_tasks:
            if preserve_blocked_safe(task, source="queue_rebuilder"):
                continue
            if task.status == TaskStatus.NEEDS_REVIEW and is_internal(task, state) and not protected_human_gate(task):
                task.status = TaskStatus.RETRY
                task.metadata.pop("cognitive_early_abort", None)
                task.metadata["queue_rebuilder_internal_review_recovered"] = True
                review += 1
            if task.status == TaskStatus.RUNNING and task.id not in active:
                task.status = TaskStatus.RETRY
                task.worker_id = None
                task.metadata["queue_rebuilder_orphan_running"] = True
                orphan += 1
            if task.status in {TaskStatus.WAITING, TaskStatus.BLOCKED, TaskStatus.RETRY}:
                if all(dep in state.tasks and state.tasks[dep].status in _DONE for dep in task.dependencies):
                    if task.status != TaskStatus.READY and not protected_human_gate(task):
                        task.status = TaskStatus.READY
                        task.metadata.pop("dependency_blockers", None)
                        deps += 1

        seen: set[str] = set(); new_roots: list[str] = []
        for tid in state.root_task_ids:
            if tid in seen or tid not in state.tasks:
                roots += 1; continue
            seen.add(tid); new_roots.append(tid)
        if roots:
            state.root_task_ids = new_roots
        state.metadata[self.KEY] = {
            "internal_review_recovered": review,
            "orphan_running_requeued": orphan,
            "dependencies_unblocked": deps,
            "duplicate_roots_removed": roots,
        }
        return QueueRebuildReport(review, orphan, deps, roots)
