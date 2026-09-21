from __future__ import annotations

from collections import defaultdict

from .models import ProjectState, TaskStatus
from .quality import SemanticDeduplicator


class TaskOptimizer:
    def __init__(self) -> None:
        self.dedupe = SemanticDeduplicator()

    def prune_duplicates(self, state: ProjectState, threshold: float = 0.90) -> int:
        groups: dict[str | None, list] = defaultdict(list)
        for t in state.leaf_tasks:
            if t.status in {TaskStatus.COMPLETE, TaskStatus.SUPERSEDED, TaskStatus.RUNNING}:
                continue
            groups[t.parent_id].append(t)
        pruned = 0
        for tasks in groups.values():
            # Bound fuzzy work for very large branches; exact normalized titles still catch common duplicates.
            seen_title: dict[str, object] = {}
            for i, task in enumerate(tasks):
                norm = " ".join(task.title.lower().split())
                prior = seen_title.get(norm)
                duplicate = prior
                if duplicate is None and len(tasks) <= 200:
                    duplicate = self.dedupe.find_duplicate(task, tasks[:i], threshold=threshold)
                if duplicate is not None:
                    task.status = TaskStatus.SUPERSEDED
                    task.metadata["duplicate_of"] = duplicate.id
                    pruned += 1
                else:
                    seen_title[norm] = task
        return pruned
