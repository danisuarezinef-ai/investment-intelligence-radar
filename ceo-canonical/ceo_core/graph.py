from __future__ import annotations

from datetime import datetime, timezone

from .models import ProjectState, TaskStatus
from .blocked_safe_state_v1 import preserve_blocked_safe


class TaskGraph:
    """Owns dependency/readiness semantics independently from planning."""

    def refresh(self, state: ProjectState) -> None:
        now = datetime.now(timezone.utc).timestamp()
        for root_id in state.root_task_ids:
            root = state.tasks[root_id]
            children = [state.tasks[c] for c in root.children if c in state.tasks]
            if children and all(c.status in {TaskStatus.COMPLETE, TaskStatus.PARTIAL_COMPLETE, TaskStatus.COMPLETE_WITH_UNCERTAINTY, TaskStatus.SUPERSEDED} for c in children):
                root.status = TaskStatus.COMPLETE
            elif any(c.status == TaskStatus.RUNNING for c in children):
                root.status = TaskStatus.RUNNING
            elif any(c.status == TaskStatus.READY for c in children):
                root.status = TaskStatus.READY
            elif children:
                root.status = TaskStatus.BLOCKED

        for task in state.leaf_tasks:
            if preserve_blocked_safe(task, source="task_graph"):
                continue
            if task.metadata.get("paused"):
                task.status = TaskStatus.BLOCKED
                continue
            if task.status not in {TaskStatus.WAITING, TaskStatus.BLOCKED, TaskStatus.RETRY}:
                continue
            retry_after = float(task.metadata.get("retry_after_ts", 0) or 0)
            if retry_after > now:
                task.status = TaskStatus.BLOCKED
                continue
            deps_done = all(
                dep in state.tasks and state.tasks[dep].status in {TaskStatus.COMPLETE, TaskStatus.PARTIAL_COMPLETE, TaskStatus.COMPLETE_WITH_UNCERTAINTY, TaskStatus.SUPERSEDED}
                for dep in task.dependencies
            )
            task.status = TaskStatus.READY if deps_done else TaskStatus.BLOCKED

    def downstream_count(self, state: ProjectState, task_id: str) -> int:
        reverse: dict[str, list[str]] = {}
        for task in state.leaf_tasks:
            for dep in task.dependencies:
                reverse.setdefault(dep, []).append(task.id)
        seen: set[str] = set()
        stack = list(reverse.get(task_id, []))
        while stack:
            current = stack.pop()
            if current in seen:
                continue
            seen.add(current)
            stack.extend(reverse.get(current, []))
        return len(seen)

    def audit(self, state: ProjectState) -> dict:
        missing_dependencies: list[tuple[str, str]] = []
        orphan_children: list[tuple[str, str]] = []
        for task in state.tasks.values():
            for dep in task.dependencies:
                if dep not in state.tasks:
                    missing_dependencies.append((task.id, dep))
            for child in task.children:
                if child not in state.tasks:
                    orphan_children.append((task.id, child))

        visiting: set[str] = set()
        visited: set[str] = set()
        cycles: list[list[str]] = []
        path: list[str] = []

        def dfs(tid: str) -> None:
            if tid in visiting:
                try:
                    i = path.index(tid)
                    cycles.append(path[i:] + [tid])
                except ValueError:
                    cycles.append([tid])
                return
            if tid in visited or tid not in state.tasks:
                return
            visiting.add(tid); path.append(tid)
            for dep in state.tasks[tid].dependencies:
                dfs(dep)
            path.pop(); visiting.remove(tid); visited.add(tid)

        for tid in state.tasks:
            dfs(tid)
        return {
            "valid": not (missing_dependencies or orphan_children or cycles),
            "missing_dependencies": missing_dependencies,
            "orphan_children": orphan_children,
            "cycles": cycles,
        }

    def critical_path(self, state: ProjectState) -> dict:
        """Longest dependency path by estimated/observed seconds."""
        memo: dict[str, tuple[float, list[str]]] = {}

        def weight(tid: str) -> float:
            t = state.tasks[tid]
            return float(t.actual_seconds or t.estimated_seconds or 0.0)

        def visit(tid: str, stack: set[str] | None = None) -> tuple[float, list[str]]:
            if tid in memo:
                return memo[tid]
            stack = set(stack or ())
            if tid in stack:
                return 0.0, []
            stack.add(tid)
            task = state.tasks[tid]
            best_seconds, best_path = 0.0, []
            for dep in task.dependencies:
                if dep not in state.tasks:
                    continue
                sec, path = visit(dep, stack)
                if sec > best_seconds:
                    best_seconds, best_path = sec, path
            out = (best_seconds + weight(tid), best_path + [tid])
            memo[tid] = out
            return out

        best = (0.0, [])
        for tid in state.tasks:
            cur = visit(tid)
            if cur[0] > best[0]:
                best = cur
        return {"seconds": round(best[0], 3), "task_ids": best[1]}

    def supersede_branch(self, state: ProjectState, task_id: str, reason: str = "superseded") -> int:
        if task_id not in state.tasks:
            return 0
        count = 0
        stack = [task_id]
        while stack:
            tid = stack.pop()
            task = state.tasks.get(tid)
            if not task:
                continue
            if task.status not in {TaskStatus.COMPLETE, TaskStatus.PARTIAL_COMPLETE, TaskStatus.COMPLETE_WITH_UNCERTAINTY, TaskStatus.SUPERSEDED}:
                task.status = TaskStatus.SUPERSEDED
                task.metadata["superseded_reason"] = reason
                count += 1
            stack.extend(task.children)
        return count

    def remaining_critical_path(self, state: ProjectState) -> dict:
        terminal = {TaskStatus.COMPLETE, TaskStatus.PARTIAL_COMPLETE, TaskStatus.COMPLETE_WITH_UNCERTAINTY, TaskStatus.SUPERSEDED}
        memo: dict[str, tuple[float, list[str]]] = {}
        def visit(tid: str, stack: set[str] | None = None):
            if tid in memo: return memo[tid]
            if tid not in state.tasks: return (0.0, [])
            stack = set(stack or ())
            if tid in stack: return (0.0, [])
            stack.add(tid); t = state.tasks[tid]
            self_weight = 0.0 if t.status in terminal else float(t.estimated_seconds or 0.0)
            best=(0.0,[])
            for dep in t.dependencies:
                sec,path=visit(dep,stack)
                if sec>best[0]: best=(sec,path)
            out=(best[0]+self_weight,best[1]+([tid] if self_weight else [])); memo[tid]=out; return out
        best=(0.0,[])
        for tid in state.tasks:
            cur=visit(tid)
            if cur[0]>best[0]: best=cur
        return {"seconds": round(best[0],3), "task_ids": best[1]}
