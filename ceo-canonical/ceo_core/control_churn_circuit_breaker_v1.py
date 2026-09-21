from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any

from .continuity_policy import protected_human_gate
from .models import ProjectState, TaskStatus
from .task_roles_v2 import is_internal


@dataclass(slots=True)
class CircuitBreakerReport:
    open: bool
    duplicate_internal_retired: int
    repeated_signature_count: int
    signature: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ControlChurnCircuitBreakerV1:
    KEY = "control_churn_circuit_breaker_v1"

    def __init__(self, *, trip_count: int = 12) -> None:
        self.trip_count = max(4, int(trip_count))

    @staticmethod
    def _normalized(task) -> str:
        title = " ".join(str(task.title or "").lower().split())
        for token in ("[cycle 1]", "[cycle 2]", "[cycle 3]", "[cycle 4]", "#1", "#2", "#3", "#4"):
            title = title.replace(token, "")
        return title.strip()

    def apply(self, state: ProjectState, *, productive_stalled: bool) -> CircuitBreakerReport:
        meta = state.metadata.setdefault(self.KEY, {})
        if meta.get("epoch") != "dev303-productive-resume-v1":
            meta.update({
                "epoch": "dev303-productive-resume-v1",
                "epoch_started_at": datetime.now(timezone.utc).isoformat(),
                "signature": "none",
                "repeated_signature_count": 0,
                "open": False,
            })
            state.metadata.pop("control_plane_circuit_open", None)
        candidates = [t for t in state.leaf_tasks if is_internal(t, state) and not protected_human_gate(t)]
        active = [t for t in candidates if t.status in {TaskStatus.READY, TaskStatus.RETRY, TaskStatus.RUNNING, TaskStatus.NEEDS_REVIEW, TaskStatus.BLOCKED}]
        groups: dict[str, list] = {}
        for task in active:
            groups.setdefault(self._normalized(task), []).append(task)
        retired = 0
        for key, rows in groups.items():
            rows.sort(key=lambda t: (t.status == TaskStatus.RUNNING, int(t.priority), t.created_at), reverse=True)
            for task in rows[1:]:
                if task.status == TaskStatus.RUNNING:
                    continue
                task.status = TaskStatus.SUPERSEDED
                task.metadata["superseded_reason"] = "control_churn_circuit_breaker_duplicate"
                retired += 1

        epoch_started_at = str(meta.get("epoch_started_at") or "")
        recent = [
            r for r in list(state.metadata.get("activity_timeline", []) or [])[-200:]
            if not epoch_started_at or str(r.get("ts") or "") >= epoch_started_at
        ][-100:]
        internal_events = [r for r in recent if str(r.get("kind") or "").lower() in {
            "cognitive_early_abort", "internal_early_abort_overridden", "goal_audit_gap_recovery_batch",
            "worker_watchdog_recovery", "goal_audit_review_auto_recovered", "recovery_created",
        }]
        signature_raw = "|".join(str(r.get("kind")) + ":" + str(r.get("title")) for r in internal_events[-self.trip_count:])
        signature = sha256(signature_raw.encode()).hexdigest()[:16] if signature_raw else "none"
        prior_sig = str(meta.get("signature") or "")
        repeated = int(meta.get("repeated_signature_count", 0)) + 1 if signature != "none" and signature == prior_sig else (1 if signature != "none" else 0)
        open_state = bool(productive_stalled and (len(internal_events) >= self.trip_count or repeated >= 3))
        if open_state:
            state.metadata["control_plane_circuit_open"] = {
                "signature": signature,
                "events": len(internal_events),
                "reason": "repeated internal control activity without productive progress",
            }
        elif not productive_stalled:
            state.metadata.pop("control_plane_circuit_open", None)

        meta.update({"signature": signature, "repeated_signature_count": repeated, "open": open_state, "retired": int(meta.get("retired", 0)) + retired})
        return CircuitBreakerReport(open_state, retired, repeated, signature)
