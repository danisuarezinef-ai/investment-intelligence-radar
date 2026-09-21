from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any

from .models import ProjectState, TaskStatus
from .progress_tracker import StableProgressTracker, is_control_plane


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        try:
            dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


@dataclass(slots=True)
class LivenessAssessment:
    status: str
    productive_completed: int
    productive_running: int
    seconds_since_productive_progress: float | None
    control_activity_only: bool
    stalled: bool
    reason: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class ProductiveProgressWatchdog:
    """Measures real work progress instead of scheduler/control-plane churn.

    A project is not considered healthy merely because audits/watchdogs are running.
    The clock is anchored to the latest completed non-control task.  A currently
    running productive task keeps the state active, while control-only activity can
    become a real stall after the configured grace period.
    """

    KEY = "productive_liveness_v1"

    def __init__(self, *, stall_after_seconds: float = 300.0) -> None:
        self.stall_after_seconds = max(1.0, float(stall_after_seconds))
        self.progress = StableProgressTracker()

    def assess(self, state: ProjectState, *, now: datetime | None = None, persist: bool = True) -> LivenessAssessment:
        now = (now or _now()).astimezone(timezone.utc)
        snap = self.progress.snapshot(state, persist=persist)
        productive_running = sum(
            1 for t in state.leaf_tasks
            if not is_control_plane(t) and t.status == TaskStatus.RUNNING
        )
        control_active = any(
            is_control_plane(t) and t.status in {TaskStatus.READY, TaskStatus.RUNNING, TaskStatus.RETRY}
            for t in state.leaf_tasks
        )
        last = _parse_dt(snap.get("last_productive_progress_at"))
        age = max(0.0, (now - last).total_seconds()) if last else None

        if state.paused or state.completed_at is not None:
            status, stalled, reason = "inactive", False, "project paused or complete"
        elif productive_running:
            status, stalled, reason = "productive_running", False, "productive task is executing"
        elif age is None and snap["productive_completed"] == 0:
            # New projects receive a grace period measured from project/start creation.
            anchor = state.started_at or state.created_at
            age = max(0.0, (now - anchor.astimezone(timezone.utc)).total_seconds())
            stalled = bool(control_active and age >= self.stall_after_seconds)
            status = "control_only_stall" if stalled else "warming_up"
            reason = "no productive completion yet; control activity only" if control_active else "waiting for first productive completion"
        else:
            stalled = bool(control_active and age is not None and age >= self.stall_after_seconds)
            status = "control_only_stall" if stalled else "healthy"
            reason = "control activity has not produced domain progress" if stalled else "within productive progress window"

        result = LivenessAssessment(
            status=status,
            productive_completed=int(snap["productive_completed"]),
            productive_running=productive_running,
            seconds_since_productive_progress=round(age, 3) if age is not None else None,
            control_activity_only=bool(control_active and productive_running == 0),
            stalled=stalled,
            reason=reason,
        )
        if persist:
            row = result.as_dict()
            row["checked_at"] = now.isoformat()
            state.metadata[self.KEY] = row
        return result


class RecoveryIncidentManager:
    """Progress-scoped recovery incidents with deterministic escalation stages."""

    KEY = "recovery_incidents_v1"
    STAGES = ("retry", "fresh_worker", "clean_audit", "partial_replan", "global_replan")

    @staticmethod
    def incident_id(state: ProjectState, blocker_signature: str) -> str:
        watermark = int(state.metadata.get("autonomy_recovery_progress_watermark", 0))
        raw = f"{state.id}|{blocker_signature}|{watermark}"
        return sha256(raw.encode()).hexdigest()[:20]

    def get_or_create(self, state: ProjectState, blocker_signature: str, blockers: list[str]) -> dict[str, Any]:
        iid = self.incident_id(state, blocker_signature)
        incidents = state.metadata.setdefault(self.KEY, {})
        row = incidents.get(iid)
        if row is None:
            row = {
                "id": iid,
                "blocker_signature": blocker_signature,
                "progress_watermark": int(state.metadata.get("autonomy_recovery_progress_watermark", 0)),
                "stage_index": 0,
                "attempts": {},
                "blockers": list(blockers[:50]),
                "created_at": _now().isoformat(),
                "updated_at": _now().isoformat(),
                "closed": False,
            }
            incidents[iid] = row
        return row

    def stage(self, incident: dict[str, Any]) -> str:
        idx = min(max(0, int(incident.get("stage_index", 0))), len(self.STAGES) - 1)
        return self.STAGES[idx]

    def record_attempt(self, incident: dict[str, Any], *, outcome: str = "started") -> str:
        stage = self.stage(incident)
        attempts = incident.setdefault("attempts", {})
        attempts[stage] = int(attempts.get(stage, 0)) + 1
        incident["last_outcome"] = outcome
        incident["updated_at"] = _now().isoformat()
        return stage

    def escalate(self, incident: dict[str, Any], *, reason: str) -> str:
        idx = min(int(incident.get("stage_index", 0)) + 1, len(self.STAGES) - 1)
        incident["stage_index"] = idx
        incident["escalation_reason"] = reason
        incident["updated_at"] = _now().isoformat()
        return self.STAGES[idx]

    def close_after_progress(self, state: ProjectState) -> int:
        watermark = int(state.metadata.get("autonomy_recovery_progress_watermark", 0))
        closed = 0
        for row in (state.metadata.get(self.KEY) or {}).values():
            if row.get("closed"):
                continue
            if int(row.get("progress_watermark", -1)) < watermark:
                row["closed"] = True
                row["closed_reason"] = "productive_progress"
                row["closed_at"] = _now().isoformat()
                closed += 1
        return closed
