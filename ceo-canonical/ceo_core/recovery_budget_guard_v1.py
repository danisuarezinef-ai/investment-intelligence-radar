from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
from typing import Any

from .continuity_policy import protected_human_gate
from .models import ProjectState, TaskStatus
from .task_roles_v2 import is_internal
from .blocked_safe_state_v1 import is_blocked_safe


@dataclass(slots=True)
class RecoveryBudgetReport:
    productive_watermark: int
    recovery_events: int
    active_internal_recoveries: int
    retired_excess: int
    budget_exhausted: bool
    signature: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class RecoveryBudgetGuardV1:
    """Progress-scoped hard limit for control-plane recovery churn.

    Recovery is useful only while it buys new productive progress.  The guard does
    not count forever across a project lifetime: every productive completion starts
    a new epoch.  Within one epoch the number of internal recovery attempts is
    bounded, duplicate active wrappers are retired, and protected human gates are
    never auto-superseded.
    """

    KEY = "recovery_budget_guard_v1"

    def __init__(self, *, max_recoveries_without_progress: int = 4, max_active_internal: int = 1) -> None:
        self.max_recoveries_without_progress = max(1, int(max_recoveries_without_progress))
        self.max_active_internal = max(1, int(max_active_internal))

    @staticmethod
    def _productive_completed(state: ProjectState) -> int:
        terminal = {TaskStatus.COMPLETE, TaskStatus.PARTIAL_COMPLETE, TaskStatus.COMPLETE_WITH_UNCERTAINTY}
        from .task_roles_v2 import is_productive
        return sum(1 for t in state.leaf_tasks if is_productive(t, state) and t.status in terminal)

    @staticmethod
    def _signature(state: ProjectState) -> str:
        rows: list[str] = []
        for task in state.leaf_tasks:
            if not is_internal(task, state):
                continue
            if task.status not in {TaskStatus.READY, TaskStatus.RETRY, TaskStatus.RUNNING, TaskStatus.NEEDS_REVIEW, TaskStatus.BLOCKED, TaskStatus.FAILED}:
                continue
            base = str(task.metadata.get("blocker_signature") or task.metadata.get("recovery_incident_id") or task.title).strip().lower()
            rows.append(base)
        raw = "|".join(sorted(rows)) or "no-internal-recovery"
        return sha256(raw.encode()).hexdigest()[:16]

    def apply(self, state: ProjectState) -> RecoveryBudgetReport:
        completed = self._productive_completed(state)
        meta = state.metadata.setdefault(self.KEY, {})
        created_now = int(state.metadata.get("autonomy_recovery_tasks_created", 0) or 0)
        if meta.get("epoch") != "dev303-productive-resume-v1":
            meta.update({
                "epoch": "dev303-productive-resume-v1",
                "productive_watermark": completed,
                "recoveries_at_watermark": created_now,
                "migration_existing_recoveries": created_now,
                "attempts_without_progress": 0,
                "budget_exhausted": False,
            })
        initialized = "productive_watermark" in meta
        previous = int(meta.get("productive_watermark", completed))
        if not initialized:
            meta["productive_watermark"] = completed
            meta["recoveries_at_watermark"] = created_now
            meta["migration_existing_recoveries"] = created_now
            meta["retired_excess_total"] = int(meta.get("retired_excess_total", 0))
        elif completed > previous:
            meta["productive_watermark"] = completed
            meta["recoveries_at_watermark"] = created_now
            meta["retired_excess_total"] = int(meta.get("retired_excess_total", 0))
            meta["budget_exhausted"] = False

        created = created_now
        created_since_progress = max(0, created - int(meta.get("recoveries_at_watermark", 0) or 0))

        active = [
            t for t in state.leaf_tasks
            if is_internal(t, state)
            and t.status in {TaskStatus.READY, TaskStatus.RETRY, TaskStatus.RUNNING, TaskStatus.NEEDS_REVIEW, TaskStatus.BLOCKED}
            and not protected_human_gate(t)
            and not is_blocked_safe(t)
        ]
        active.sort(key=lambda t: (-int(t.priority), t.created_at))
        # Attempt accounting is progress-epoch scoped. Historical recovery events
        # remain useful for observability, but must not poison a later epoch after
        # genuine productive progress.
        attempts = max(created_since_progress, len(active))
        retired = 0
        # Keep only a tiny number of simultaneous recovery/control units.  This does
        # not delete history; excess wrappers become SUPERSEDED with an audit marker.
        for task in active[self.max_active_internal:]:
            if task.status == TaskStatus.RUNNING:
                continue
            task.status = TaskStatus.SUPERSEDED
            task.metadata["superseded_reason"] = "recovery_budget_guard_duplicate_internal_control"
            task.metadata["recovery_budget_guard_retired"] = True
            retired += 1

        exhausted = attempts >= self.max_recoveries_without_progress
        if exhausted:
            state.metadata["control_plane_recovery_budget_exhausted"] = {
                "productive_watermark": completed,
                "attempts_without_progress": attempts,
                "max": self.max_recoveries_without_progress,
                "signature": self._signature(state),
            }
        else:
            state.metadata.pop("control_plane_recovery_budget_exhausted", None)

        meta["budget_exhausted"] = exhausted
        meta["attempts_without_progress"] = attempts
        meta["retired_excess_total"] = int(meta.get("retired_excess_total", 0)) + retired
        meta["signature"] = self._signature(state)
        return RecoveryBudgetReport(
            productive_watermark=completed,
            recovery_events=attempts,
            active_internal_recoveries=max(0, len(active) - retired),
            retired_excess=retired,
            budget_exhausted=exhausted,
            signature=meta["signature"],
        )
