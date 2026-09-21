from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any

from .decomposition_v3 import AdaptiveTaskDecomposer
from .models import ProjectState, Task, TaskStatus
from .quality import SemanticDeduplicator
from .blocked_safe_state_v1 import is_blocked_safe


_MUTABLE = {TaskStatus.WAITING, TaskStatus.READY, TaskStatus.BLOCKED, TaskStatus.RETRY}


@dataclass(slots=True)
class TreeMaintenanceReport:
    structural_repairs: int = 0
    deduplicated: int = 0
    adaptive_splits: int = 0
    stale_roots_removed: int = 0

    def to_dict(self) -> dict[str, int]:
        return asdict(self)


class DynamicTaskTreeManager:
    """Keeps Goal -> branches -> leaves useful as work is discovered.

    Mutations are deliberately bounded and never supersede running/completed tasks or
    anything with explicit external/irreversible semantics.
    """

    def __init__(self) -> None:
        self.decomposer = AdaptiveTaskDecomposer()
        self.dedupe = SemanticDeduplicator()

    def maintain(self, state: ProjectState, *, max_splits: int = 4, max_dedupes: int = 20) -> TreeMaintenanceReport:
        report = TreeMaintenanceReport()
        report.structural_repairs += self._repair_parent_child_links(state)
        report.stale_roots_removed += self._clean_roots(state)
        report.deduplicated += self._dedupe_pending(state, max_dedupes=max_dedupes)
        report.adaptive_splits += self._bounded_refine(state, max_splits=max_splits)
        state.metadata["dynamic_task_tree_last"] = report.to_dict()
        return report

    def attach_discovered(self, state: ProjectState, parent: Task, children: list[Task]) -> int:
        attached = 0
        for child in children:
            if child.id not in state.tasks:
                state.tasks[child.id] = child
            if child.parent_id is None:
                child.parent_id = parent.id
            if child.parent_id == parent.id and child.id not in parent.children:
                parent.children.append(child.id)
                attached += 1
            child.depth = max(parent.depth + 1, child.depth)
        return attached

    def _repair_parent_child_links(self, state: ProjectState) -> int:
        repairs = 0
        for task in state.tasks.values():
            if task.parent_id and task.parent_id in state.tasks:
                parent = state.tasks[task.parent_id]
                if task.id not in parent.children:
                    parent.children.append(task.id)
                    repairs += 1
            valid_children = [cid for cid in task.children if cid in state.tasks]
            if len(valid_children) != len(task.children):
                repairs += len(task.children) - len(valid_children)
                task.children = valid_children
        return repairs

    @staticmethod
    def _clean_roots(state: ProjectState) -> int:
        before = len(state.root_task_ids)
        seen: set[str] = set()
        roots: list[str] = []
        for tid in state.root_task_ids:
            if tid in state.tasks and tid not in seen:
                roots.append(tid); seen.add(tid)
        for task in state.tasks.values():
            if task.parent_id is None and task.id not in seen:
                roots.append(task.id); seen.add(task.id)
        state.root_task_ids = roots
        return max(0, before - len(roots))

    def _dedupe_pending(self, state: ProjectState, *, max_dedupes: int) -> int:
        changed = 0
        candidates = [t for t in state.leaf_tasks if t.status in _MUTABLE and not self._protected(t)]
        accepted_by_key: dict[str, list[Task]] = {}
        threshold = float(state.metadata.get("dynamic_tree_dedupe_threshold", 0.93))
        for task in sorted(candidates, key=lambda t: (-int(t.priority), t.created_at)):
            if changed >= max_dedupes:
                break
            duplicate = None
            task_key = self._dedupe_identity(task)
            bucket = accepted_by_key.setdefault(task_key, [])
            for other in bucket:
                same_branch = task.parent_id == other.parent_id or bool(task.metadata.get("dedupe_across_branches"))
                if not same_branch:
                    continue
                score = self.dedupe.score(
                    f"{task.title} {task.description}",
                    f"{other.title} {other.description}",
                )
                if score >= threshold:
                    duplicate = other
                    break
            if duplicate is None:
                bucket.append(task)
                continue
            # Keep the higher-value earlier candidate; preserve dependencies that are
            # not already represented by the survivor.
            duplicate.dependencies = sorted(set(duplicate.dependencies) | set(task.dependencies))
            task.status = TaskStatus.SUPERSEDED
            task.metadata["superseded_reason"] = "dynamic_tree_semantic_duplicate"
            task.metadata["superseded_by"] = duplicate.id
            changed += 1
        return changed

    @staticmethod
    def _dedupe_identity(task: Task) -> str:
        explicit = task.metadata.get("dedupe_key")
        if explicit:
            return " ".join(str(explicit).lower().split())
        # Keep digits: numbered/partitioned work units are often intentionally distinct.
        import re
        return re.sub(r"[^a-z0-9áéíóúüñ]+", " ", task.title.lower()).strip()

    def _bounded_refine(self, state: ProjectState, *, max_splits: int) -> int:
        changed = 0
        for task in list(state.leaf_tasks):
            if changed >= max_splits:
                break
            if task.status not in _MUTABLE or self._protected(task):
                continue
            assessment = self.decomposer.estimator.assess(task)
            if assessment.too_large and not task.metadata.get("adaptive_split_of"):
                if self.decomposer.split(state, task, assessment.recommended_parts):
                    changed += 1
        return changed

    @staticmethod
    def _protected(task: Task) -> bool:
        md = task.metadata
        return bool(is_blocked_safe(task) or md.get("external_action") or md.get("irreversible") or md.get("destructive") or md.get("spending") or md.get("public_release") or md.get("control_plane_atomic") or md.get("goal_continuity_audit"))
