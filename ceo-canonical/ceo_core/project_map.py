from __future__ import annotations

from .graph import TaskGraph
from .models import ProjectState, TaskStatus


class ProjectMapBuilder:
    """Compact graph view for the optional live project visualization."""
    def __init__(self) -> None: self.graph = TaskGraph()
    def build(self, state: ProjectState, max_nodes: int = 600) -> dict:
        critical = set(self.graph.remaining_critical_path(state).get("task_ids", []))
        nodes = []
        edges = []
        selected = []
        for t in state.tasks.values():
            if len(selected) >= max_nodes: break
            if t.parent_id is None or t.status in {TaskStatus.RUNNING, TaskStatus.FAILED, TaskStatus.NEEDS_REVIEW} or t.id in critical or t.depth <= 2:
                selected.append(t)
        selected_ids = {t.id for t in selected}
        for t in selected:
            nodes.append({"id": t.id, "title": t.title, "status": t.status.value, "critical": t.id in critical, "depth": t.depth})
            if t.parent_id and t.parent_id in selected_ids:
                edges.append({"from": t.parent_id, "to": t.id, "kind": "parent"})
            for dep in t.dependencies:
                if dep in selected_ids:
                    edges.append({"from": dep, "to": t.id, "kind": "dependency"})
        return {"nodes": nodes, "edges": edges, "truncated": len(state.tasks) > len(nodes), "total_tasks": len(state.tasks)}
