from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .models import ProjectState, TaskStatus
from .task_roles_v2 import is_internal, is_productive


@dataclass(slots=True)
class ProductiveProgressReport:
    productive_completed: int
    productive_running: int
    productive_ready: int
    internal_active: int
    no_progress_cycles: int
    control_only_cycles: int
    stalled: bool
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ProductiveProgressGuardV1:
    """Tick-based productivity watchdog independent from wall-clock/provider latency."""

    KEY = "productive_progress_guard_v1"

    def __init__(self, *, stall_cycles: int = 300, control_only_cycles: int = 150) -> None:
        self.stall_cycles = max(3, int(stall_cycles))
        self.control_only_limit = max(3, int(control_only_cycles))

    def assess(self, state: ProjectState) -> ProductiveProgressReport:
        terminal = {TaskStatus.COMPLETE, TaskStatus.PARTIAL_COMPLETE, TaskStatus.COMPLETE_WITH_UNCERTAINTY}
        completed = sum(1 for t in state.leaf_tasks if is_productive(t, state) and t.status in terminal)
        running = sum(1 for t in state.leaf_tasks if is_productive(t, state) and t.status == TaskStatus.RUNNING)
        ready = sum(1 for t in state.leaf_tasks if is_productive(t, state) and t.status in {TaskStatus.READY, TaskStatus.RETRY})
        internal_active = sum(1 for t in state.leaf_tasks if is_internal(t, state) and t.status in {TaskStatus.READY, TaskStatus.RETRY, TaskStatus.RUNNING, TaskStatus.NEEDS_REVIEW})

        meta = state.metadata.setdefault(self.KEY, {})
        if meta.get("epoch") != "dev303-productive-resume-v1":
            meta.update({
                "epoch": "dev303-productive-resume-v1",
                "historical_ticks_before_epoch": int(meta.get("ticks", 0) or 0),
                "historical_no_progress_cycles_before_epoch": int(meta.get("no_progress_cycles", 0) or 0),
                "historical_control_only_cycles_before_epoch": int(meta.get("control_only_cycles", 0) or 0),
                "ticks": 0,
                "last_productive_completed": completed,
                "no_progress_cycles": 0,
                "control_only_cycles": 0,
                "stalled": False,
                "reason": "reliability epoch migrated",
            })
        previous_completed = int(meta.get("last_productive_completed", completed))
        if completed > previous_completed:
            no_progress = 0
            control_only = 0
            meta["last_progress_tick"] = int(meta.get("ticks", 0))
        else:
            no_progress = int(meta.get("no_progress_cycles", 0)) + 1
            control_only = int(meta.get("control_only_cycles", 0)) + 1 if internal_active and not running else 0

        ticks = int(meta.get("ticks", 0)) + 1
        stalled = False
        reason = "healthy"
        if state.paused or state.completed_at is not None:
            no_progress = 0; control_only = 0; reason = "inactive"
        elif running:
            reason = "productive worker active"
        elif ready and no_progress >= self.stall_cycles:
            stalled = True; reason = "productive work is ready but no worker has completed progress"
        elif internal_active and control_only >= self.control_only_limit:
            stalled = True; reason = "control-plane activity without productive progress"

        meta.update({
            "ticks": ticks,
            "last_productive_completed": completed,
            "no_progress_cycles": no_progress,
            "control_only_cycles": control_only,
            "stalled": stalled,
            "reason": reason,
        })
        return ProductiveProgressReport(completed, running, ready, internal_active, no_progress, control_only, stalled, reason)
