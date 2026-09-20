from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone

from .graph import TaskGraph
from .models import ProjectState, Task, TaskStatus
from .blocked_safe_state_v1 import is_blocked_safe


@dataclass(slots=True)
class ReplanAction:
    action: str
    task_id: str | None
    reason: str
    payload: dict


class ReplanningEngine:
    """Produces bounded plan changes from observed failures, conflicts and saturation."""

    def __init__(self) -> None:
        self.graph = TaskGraph()

    def inspect(self, state: ProjectState, max_actions: int = 25) -> list[ReplanAction]:
        actions: list[ReplanAction] = []
        leaves=list(state.leaf_tasks)
        # Recovery actions are prioritized so routine blocked/retry work cannot starve a
        # terminal failure and leave the whole project alive forever.
        for task in leaves:
            if len(actions) >= max_actions: break
            exhausted = task.status == TaskStatus.FAILED and task.attempts >= task.max_attempts
            can_replace = int(task.metadata.get("recovery_generation",0)) < int(state.metadata.get("max_recovery_generations",2))
            if exhausted and can_replace and (task.metadata.get("failure_split_exhausted") or int(task.metadata.get("failure_count",0)) < 2 or task.depth >= int(state.metadata.get("max_failure_split_depth",2))):
                actions.append(ReplanAction("replace_exhausted", task.id, "execution_exhausted", {}))
            elif task.status == TaskStatus.FAILED and int(task.metadata.get("failure_count", 0)) >= 2 and not task.metadata.get("failure_recovered_by_split"):
                actions.append(ReplanAction("split_failed", task.id, "repeated_failure", {}))
        for task in leaves:
            if len(actions) >= max_actions: break
            if task.status == TaskStatus.NEEDS_REVIEW and task.metadata.get("completion_rejected"):
                actions.append(ReplanAction("repair_completion", task.id, "completion_audit_rejected", {"reasons": task.metadata.get("completion_rejected")}))
        now=datetime.now(timezone.utc).timestamp()
        for task in leaves:
            if len(actions) >= max_actions: break
            retry_after=float(task.metadata.get("retry_after_ts",0) or 0)
            if task.status == TaskStatus.BLOCKED and not task.dependencies and not task.metadata.get("paused") and not is_blocked_safe(task) and retry_after <= now:
                actions.append(ReplanAction("unblock", task.id, "blocked_without_dependencies", {}))
        for pair, review_id in list((state.metadata.get("conflict_reviews") or {}).items()):
            review = state.tasks.get(review_id)
            if review and review.status == TaskStatus.FAILED and len(actions) < max_actions:
                actions.append(ReplanAction("retry_conflict", review_id, "unresolved_conflict", {"pair": pair}))
        if state.metadata.get("knowledge_saturated") and len(actions) < max_actions:
            actions.append(ReplanAction("reduce_exploration", None, "low_marginal_yield", {"from": state.exploration_percent}))

        budget = state.metadata.get("budget_snapshot") or {}
        if float(budget.get("pressure", 0.0) or 0.0) >= 0.85 and state.priority_mode != "cost_min" and len(actions) < max_actions:
            actions.append(ReplanAction("budget_pressure", None, "budget_pressure_high", {"pressure": float(budget.get("pressure", 0.0))}))

        if state.deadline and len(actions) < max_actions:
            try:
                deadline = datetime.fromisoformat(state.deadline.replace("Z", "+00:00"))
                if deadline.tzinfo is None:
                    deadline = deadline.replace(tzinfo=timezone.utc)
                hours_left = (deadline - datetime.now(timezone.utc)).total_seconds() / 3600.0
                unfinished = any(t.status not in {TaskStatus.COMPLETE, TaskStatus.PARTIAL_COMPLETE, TaskStatus.COMPLETE_WITH_UNCERTAINTY, TaskStatus.SUPERSEDED} for t in leaves)
                if unfinished and hours_left <= 24 and state.priority_mode != "speed":
                    actions.append(ReplanAction("deadline_pressure", None, "deadline_within_24h", {"hours_left": round(hours_left, 2)}))
            except ValueError:
                pass
        return actions

    def apply(self, state: ProjectState, actions: list[ReplanAction], decomposer=None) -> int:
        changed = 0
        for action in actions:
            task = state.tasks.get(action.task_id) if action.task_id else None
            if action.action == "replace_exhausted" and task is not None:
                generation=int(task.metadata.get("recovery_generation",0))+1
                replacement=Task(
                    title=task.title,
                    description=task.description,
                    parent_id=task.parent_id,
                    depth=task.depth,
                    priority=min(100,task.priority+3),
                    dependencies=list(task.dependencies),
                    estimated_seconds=task.estimated_seconds,
                    required_capabilities=list(task.required_capabilities),
                    acceptance_criteria=list(task.acceptance_criteria),
                    max_attempts=max(task.max_attempts,4),
                    metadata={k:v for k,v in task.metadata.items() if k not in {"failure_count","failure_split_exhausted","avoid_providers","retry_after_ts","assigned_node"}},
                )
                replacement.metadata.update({"recovery_of":task.id,"recovery_generation":generation})
                state.tasks[replacement.id]=replacement
                if task.parent_id and task.parent_id in state.tasks:
                    parent=state.tasks[task.parent_id]
                    parent.children=[replacement.id if x==task.id else x for x in parent.children]
                else:
                    state.root_task_ids=[replacement.id if x==task.id else x for x in state.root_task_ids]
                task.status=TaskStatus.SUPERSEDED
                task.metadata["superseded_by_recovery"]=replacement.id
                changed += 1
            elif action.action == "split_failed" and task is not None and decomposer is not None:
                children = decomposer.split_failed(state, task)
                changed += int(bool(children))
            elif action.action == "repair_completion" and task is not None:
                task.metadata["next_instruction"] = "Repair the result to satisfy the completion audit. Address every rejected criterion explicitly."
                task.status = TaskStatus.READY
                changed += 1
            elif action.action == "unblock" and task is not None and not is_blocked_safe(task):
                task.status = TaskStatus.READY
                changed += 1
            elif action.action == "retry_conflict" and task is not None and task.attempts < task.max_attempts:
                task.status = TaskStatus.RETRY
                changed += 1
            elif action.action == "reduce_exploration":
                new_value = max(5, state.exploration_percent - 10)
                changed += int(new_value != state.exploration_percent)
                state.exploration_percent = new_value
            elif action.action == "budget_pressure":
                if state.priority_mode != "cost_min":
                    state.metadata.setdefault("priority_mode_before_budget_pressure", state.priority_mode)
                    state.priority_mode = "cost_min"
                    state.exploration_percent = max(5, state.exploration_percent - 10)
                    changed += 1
            elif action.action == "deadline_pressure":
                if state.priority_mode != "speed":
                    state.metadata.setdefault("priority_mode_before_deadline_pressure", state.priority_mode)
                    state.priority_mode = "speed"
                    state.exploration_percent = max(5, state.exploration_percent - 10)
                    for leaf in state.leaf_tasks:
                        if leaf.status in {TaskStatus.READY, TaskStatus.WAITING, TaskStatus.BLOCKED, TaskStatus.RETRY}:
                            leaf.priority = min(100, leaf.priority + 10)
                    changed += 1
        if actions:
            hist = state.metadata.setdefault("replan_history", [])
            if changed:
                state.metadata["plan_revision"] = int(state.metadata.get("plan_revision", 0)) + 1
            hist.append({"ts": datetime.now(timezone.utc).isoformat(), "actions": [asdict(a) for a in actions], "changed": changed, "revision": int(state.metadata.get("plan_revision", 0))})
            del hist[:-200]
        return changed
