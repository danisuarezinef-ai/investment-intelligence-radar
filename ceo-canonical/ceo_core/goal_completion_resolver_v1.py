from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

from .continuity_policy import protected_human_gate
from .models import ProjectState, TaskStatus
from .task_roles_v2 import is_productive, is_internal


@dataclass(slots=True)
class GoalResolutionReport:
    action: str
    productive_open: int
    internal_open: int
    human_gate_open: int
    changed: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class GoalCompletionResolverV1:
    """Prevent 99%-forever states while preserving explicit goal-audit semantics."""

    KEY = "goal_completion_resolver_v1"

    def resolve(self, state: ProjectState) -> GoalResolutionReport:
        terminal = {TaskStatus.COMPLETE, TaskStatus.PARTIAL_COMPLETE, TaskStatus.COMPLETE_WITH_UNCERTAINTY, TaskStatus.SUPERSEDED}
        productive_open = [t for t in state.leaf_tasks if is_productive(t, state) and t.status not in terminal]
        internal_open = [t for t in state.leaf_tasks if is_internal(t, state) and t.status not in terminal]
        human_open = [t for t in state.leaf_tasks if t.status == TaskStatus.NEEDS_REVIEW and protected_human_gate(t)]
        changed = 0
        action = "continue"

        # Goal audit PASS is the only autonomous completion authority.  If it is
        # durable and there is no remaining productive/human work, close the goal.
        if not productive_open and not human_open and bool(state.metadata.get("goal_audit_passed")):
            if state.completed_at is None:
                state.completed_at = datetime.now(timezone.utc)
                changed = 1
            action = "complete"
            state.metadata.pop("autonomy_stalled", None)
        elif not productive_open and not human_open:
            action = "needs_continuity_audit"
            state.metadata["goal_closure_pending"] = True
        else:
            state.metadata.pop("goal_closure_pending", None)

        state.metadata[self.KEY] = {
            "action": action,
            "productive_open": len(productive_open),
            "internal_open": len(internal_open),
            "human_gate_open": len(human_open),
            "changed": changed,
        }
        return GoalResolutionReport(action, len(productive_open), len(internal_open), len(human_open), changed)
