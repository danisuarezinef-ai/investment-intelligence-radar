from __future__ import annotations

from dataclasses import dataclass, asdict
from math import ceil
from typing import Iterable

from .models import ProjectState, Task, TaskStatus


@dataclass(slots=True)
class DirectorNode:
    id: str
    title: str
    level: int
    task_ids: list[str]
    parent_id: str | None = None
    child_ids: list[str] | None = None
    workload: int = 0
    progress: float = 0.0
    blocked: int = 0


class ProjectDirector:
    """Builds a lightweight management hierarchy above workers.

    The hierarchy is derived from the task graph and kept in project metadata, so it
    survives restarts without becoming another source of truth for task state.
    """

    def __init__(self, span: int = 24) -> None:
        self.span = max(4, span)

    def rebuild(self, state: ProjectState) -> dict[str, dict]:
        nodes: dict[str, DirectorNode] = {}
        root_groups: list[str] = []
        roots = [rid for rid in state.root_task_ids if rid in state.tasks]
        # Normal projects use one director per major root phase. Synthetic/flat projects
        # are grouped into bounded portfolios so the management layer remains O(n/span).
        flat = len(roots) > self.span * 4 and all(not state.tasks[r].children for r in roots[: min(len(roots), self.span * 4 + 1)])
        if flat:
            for block_i in range(0, len(roots), self.span * self.span):
                block = roots[block_i:block_i + self.span * self.span]
                did = f"director:portfolio:{block_i // (self.span * self.span)}"
                team_ids: list[str] = []
                for i in range(0, len(block), self.span):
                    chunk = block[i:i + self.span]
                    tid = f"team:portfolio:{block_i // (self.span * self.span)}:{i // self.span}"
                    nodes[tid] = self._node(state, tid, f"Team {i // self.span + 1}", 2, chunk, parent_id=did)
                    team_ids.append(tid)
                dnode = self._node(state, did, f"Portfolio {block_i // (self.span * self.span) + 1}", 1, block, parent_id="ceo")
                dnode.child_ids = team_ids; nodes[did] = dnode; root_groups.append(did)
        else:
            for root_id in roots:
                root = state.tasks[root_id]
                leaf_ids = self._leaves(state, root_id) or [root_id]
                team_ids: list[str] = []
                for i in range(0, len(leaf_ids), self.span):
                    chunk = leaf_ids[i:i + self.span]
                    tid = f"team:{root_id}:{i // self.span}"
                    node = self._node(state, tid, f"Team {i // self.span + 1}: {root.title}", 2, chunk, parent_id=f"director:{root_id}")
                    nodes[tid] = node; team_ids.append(tid)
                did = f"director:{root_id}"
                dnode = self._node(state, did, root.title, 1, leaf_ids, parent_id="ceo")
                dnode.child_ids = team_ids; nodes[did] = dnode; root_groups.append(did)
        all_leaf_ids = [t.id for t in state.leaf_tasks]
        ceo = self._node(state, "ceo", state.goal or "Project", 0, all_leaf_ids)
        ceo.child_ids = root_groups; nodes["ceo"] = ceo
        payload = {k: asdict(v) for k, v in nodes.items()}
        state.metadata["director_tree"] = payload
        return payload

    def _node(self, state: ProjectState, node_id: str, title: str, level: int, ids: list[str], parent_id: str | None = None) -> DirectorNode:
        tasks = [state.tasks[i] for i in ids if i in state.tasks]
        terminal = {TaskStatus.COMPLETE, TaskStatus.PARTIAL_COMPLETE, TaskStatus.COMPLETE_WITH_UNCERTAINTY, TaskStatus.SUPERSEDED}
        completed = sum(t.status in terminal for t in tasks)
        blocked = sum(t.status in {TaskStatus.BLOCKED, TaskStatus.NEEDS_REVIEW, TaskStatus.FAILED} for t in tasks)
        progress = (100.0 * completed / len(tasks)) if tasks else 0.0
        return DirectorNode(node_id, title, level, list(ids), parent_id, [], len(tasks), round(progress, 2), blocked)

    def _leaves(self, state: ProjectState, task_id: str) -> list[str]:
        out: list[str] = []
        stack = [task_id]
        seen: set[str] = set()
        while stack:
            tid = stack.pop()
            if tid in seen:
                continue
            seen.add(tid)
            task = state.tasks.get(tid)
            if not task:
                continue
            if task.children:
                stack.extend(task.children)
            else:
                out.append(tid)
        return out

    def supervision_load(self, state: ProjectState) -> dict[str, float]:
        tree = state.metadata.get("director_tree") or self.rebuild(state)
        return {nid: round(float(node.get("workload", 0)) * (1 + float(node.get("blocked", 0)) / max(1, float(node.get("workload", 1)))), 2) for nid, node in tree.items()}
