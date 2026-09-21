from __future__ import annotations

from difflib import SequenceMatcher

from .graph import TaskGraph
from .models import ProjectState, TaskStatus


class GoalRevisionManager:
    """Safely revises a goal and invalidates only work likely affected."""
    def revise(self, state: ProjectState, new_goal: str) -> dict:
        old = state.goal
        similarity = SequenceMatcher(None, old.lower(), new_goal.lower()).ratio() if old else 0.0
        state.goal = new_goal.strip()
        state.goal_definition = new_goal.strip()
        invalidated = 0
        if similarity < 0.65:
            for task in state.leaf_tasks:
                if task.status not in {TaskStatus.COMPLETE, TaskStatus.SUPERSEDED}:
                    task.status = TaskStatus.WAITING
                    task.conversation_id = None
                    task.metadata["goal_revision"] = True
                    invalidated += 1
        state.metadata.setdefault("goal_history", []).append({"old": old, "new": new_goal, "similarity": similarity})
        return {"similarity": round(similarity, 3), "invalidated": invalidated}


class SelectivePause:
    def pause_branch(self, state: ProjectState, task_id: str) -> int:
        return self._set(state, task_id, True)

    def resume_branch(self, state: ProjectState, task_id: str) -> int:
        return self._set(state, task_id, False)

    def _set(self, state: ProjectState, task_id: str, paused: bool) -> int:
        count = 0; stack = [task_id]
        while stack:
            tid = stack.pop(); task = state.tasks.get(tid)
            if not task: continue
            task.metadata["paused"] = paused; count += 1; stack.extend(task.children)
        return count


class AutonomyPolicy:
    LEVELS = {"trivial": 0.2, "normal": 0.5, "important": 0.75, "irreversible": 1.1}

    def can_auto_decide(self, state: ProjectState, importance: str, confidence: float | None = None) -> bool:
        if not state.autonomy_enabled:
            return False
        threshold = self.LEVELS.get(importance, 0.75)
        configured = float(state.metadata.get("autonomy_threshold", 0.72))
        if importance == "irreversible":
            return False
        return (confidence or 0.0) >= max(threshold, configured)
