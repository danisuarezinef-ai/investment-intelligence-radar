from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

from .models import ProjectState, TaskStatus
from .task_roles_v2 import is_internal, is_productive


@dataclass(slots=True)
class ProductiveTruthReport:
    status: str
    productive_completed: int
    productive_running: int
    productive_ready: int
    internal_active: int
    worker_recoveries: int
    useful_output_rate: float
    stalled: bool
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ProductiveTruthV2:
    """Operator truth: activity is not productivity.

    A provider/recovery worker may be busy while the project produces nothing.  This
    classifier deliberately refuses to call such a state WORKING once recovery churn
    crosses a small bound without a productive completion.
    """

    KEY = "productive_truth_v2"

    def __init__(self, *, recovery_trip: int = 4) -> None:
        self.recovery_trip = max(2, int(recovery_trip))

    @staticmethod
    def _terminal(status: TaskStatus) -> bool:
        return status in {TaskStatus.COMPLETE, TaskStatus.PARTIAL_COMPLETE, TaskStatus.COMPLETE_WITH_UNCERTAINTY}

    def assess(self, state: ProjectState) -> ProductiveTruthReport:
        productive = [t for t in state.leaf_tasks if is_productive(t, state) and t.status != TaskStatus.SUPERSEDED]
        completed = sum(self._terminal(t.status) for t in productive)
        running = sum(t.status == TaskStatus.RUNNING for t in productive)
        ready = sum(t.status in {TaskStatus.READY, TaskStatus.RETRY} for t in productive)
        internal_active = sum(
            is_internal(t, state) and t.status in {TaskStatus.READY, TaskStatus.RETRY, TaskStatus.RUNNING, TaskStatus.BLOCKED, TaskStatus.NEEDS_REVIEW}
            for t in state.leaf_tasks
        )
        recoveries_total = int(state.metadata.get("worker_recoveries", 0) or 0)
        meta = state.metadata.setdefault(self.KEY, {})
        if meta.get("epoch") != "dev308-executable-route-integrity-v1":
            meta.update({
                "epoch": "dev308-executable-route-integrity-v1",
                "productive_watermark": completed,
                "recoveries_at_watermark": recoveries_total,
                "historical_recoveries_before_epoch": recoveries_total,
            })
        prior_completed = int(meta.get("productive_watermark", completed))
        if completed > prior_completed:
            meta["productive_watermark"] = completed
            meta["recoveries_at_watermark"] = recoveries_total
        elif "productive_watermark" not in meta:
            meta["productive_watermark"] = completed
            meta["recoveries_at_watermark"] = recoveries_total
        recoveries = max(0, recoveries_total - int(meta.get("recoveries_at_watermark", 0) or 0))

        tp = state.metadata.get("productive_throughput_last") or {}
        useful_rate = float(tp.get("useful_units_per_hour", tp.get("tasks_per_hour", 0.0)) or 0.0)
        stalled = False
        reason = "healthy"
        status = "working" if running else ("planning" if ready else "idle")
        provider_wait = dict(state.metadata.get("provider_wait_v1") or {})
        if provider_wait.get("active") and not running:
            status = "waiting_provider"
            stalled = False
            reason = "provider temporarily unavailable: " + str(provider_wait.get("category") or "unavailable")
        if state.paused:
            status, reason = "paused", "project paused"
        elif state.completed_at is not None:
            status, reason = "complete", "objective completed"
        elif provider_wait.get("active") and not running:
            pass
        elif completed == 0 and recoveries >= self.recovery_trip and internal_active and not running and ready == 0:
            stalled = True
            status = "stalled"
            reason = f"{recoveries} recoveries without any productive completion"
        elif useful_rate <= 0 and recoveries >= self.recovery_trip and internal_active and not running and ready == 0:
            stalled = True
            status = "stalled"
            reason = "control/recovery activity without useful output"

        row = ProductiveTruthReport(status, completed, running, ready, internal_active, recoveries, useful_rate, stalled, reason)
        meta.update({**row.to_dict(), "checked_at": datetime.now(timezone.utc).isoformat()})
        return row
