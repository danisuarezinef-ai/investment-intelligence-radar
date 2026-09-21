from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any

from .models import ProjectState, Task, TaskStatus
from .task_roles_v2 import is_productive


@dataclass(slots=True)
class RecoveryStormReport:
    open: bool
    recoveries_without_progress: int
    productive_watermark: int
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class RecoveryStormGuardV1:
    """Fail-closed guard for repeated automatic recovery without useful output.

    This guard intentionally counts the live-worker recovery counter rather than only
    autonomy wrapper tasks. The field incident that motivated it involved repeated
    orphan-worker retries, which bypassed the older control-plane recovery budget.
    """

    KEY = "recovery_storm_guard_v1"

    def __init__(self, *, global_trip: int = 8, per_task_trip: int = 4, repeat_trip: int = 2) -> None:
        self.global_trip = max(4, int(global_trip))
        self.per_task_trip = max(2, int(per_task_trip))
        self.repeat_trip = max(2, int(repeat_trip))

    @staticmethod
    def productive_completed(state: ProjectState) -> int:
        terminal = {TaskStatus.COMPLETE, TaskStatus.PARTIAL_COMPLETE, TaskStatus.COMPLETE_WITH_UNCERTAINTY}
        return sum(1 for t in state.leaf_tasks if is_productive(t, state) and t.status in terminal)

    @staticmethod
    def fingerprint(task: Task, *, reason: str, provider: str | None = None, strategy: str | None = None) -> str:
        raw = "|".join([task.id, str(reason or "").strip().lower(), str(provider or task.provider_name or "").strip().lower(), str(strategy or task.metadata.get("recovery_strategy") or "default").strip().lower()])
        return sha256(raw.encode("utf-8")).hexdigest()[:20]

    def record_task_recovery(self, task: Task, *, reason: str, provider: str | None = None, strategy: str | None = None) -> dict[str, Any]:
        meta = task.metadata.setdefault(self.KEY, {})
        count = int(meta.get("count", 0) or 0) + 1
        fp = self.fingerprint(task, reason=reason, provider=provider, strategy=strategy)
        last_fp = str(meta.get("last_fingerprint") or "")
        repeat = int(meta.get("repeat_count", 0) or 0) + 1 if fp == last_fp else 1
        meta.update({"count": count, "last_fingerprint": fp, "repeat_count": repeat, "last_reason": reason, "last_provider": provider or task.provider_name, "last_at": datetime.now(timezone.utc).isoformat()})
        exhausted = count >= self.per_task_trip
        must_change = repeat >= self.repeat_trip
        return {"count": count, "repeat_count": repeat, "fingerprint": fp, "must_change_strategy": must_change, "exhausted": exhausted}

    def assess(self, state: ProjectState) -> RecoveryStormReport:
        completed = self.productive_completed(state)
        total = int(state.metadata.get("worker_recoveries", 0) or 0)
        meta = state.metadata.setdefault(self.KEY, {})
        if meta.get("epoch") != "dev303-productive-resume-v1":
            meta.update({
                "epoch": "dev303-productive-resume-v1",
                "productive_watermark": completed,
                "recoveries_at_watermark": total,
                "historical_recoveries_before_epoch": total,
                "recoveries_without_progress": 0,
                "open": False,
                "reason": "reliability epoch migrated",
            })
            state.metadata.pop("recovery_storm_breaker", None)
            state.metadata.pop("recovery_storm_suppression_owner", None)
        prior = int(meta.get("productive_watermark", completed) or 0)
        if "productive_watermark" not in meta:
            # Upgrade migration: historical recoveries are evidence, not a reason to
            # brick the newly upgraded runtime. Start a fresh bounded epoch at the
            # current counter; only recoveries produced after this guard is active
            # can trip the breaker.
            meta["productive_watermark"] = completed
            meta["recoveries_at_watermark"] = total
        elif completed > prior:
            meta["productive_watermark"] = completed
            meta["recoveries_at_watermark"] = total
            meta["open"] = False
            state.metadata.pop("recovery_storm_breaker", None)
            if state.metadata.pop("recovery_storm_suppression_owner", False):
                state.metadata.pop("suppress_new_internal_recovery", None)
            if state.metadata.get("operator_productivity_state") == "BLOQUEADO":
                state.metadata["operator_productivity_state"] = "ACTIVO"
            state.metadata["recovery_storm_closed_at"] = datetime.now(timezone.utc).isoformat()
        since = max(0, total - int(meta.get("recoveries_at_watermark", 0) or 0))
        opened = since >= self.global_trip
        reason = "within recovery budget"
        if opened:
            reason = f"{since} worker recoveries without productive completion"
            row = {"open": True, "recoveries_without_progress": since, "trip": self.global_trip, "reason": reason, "ts": datetime.now(timezone.utc).isoformat()}
            state.metadata["recovery_storm_breaker"] = row
            state.metadata["suppress_new_internal_recovery"] = True
            state.metadata["recovery_storm_suppression_owner"] = True
            state.metadata["operator_productivity_state"] = "BLOQUEADO"
        meta.update({"open": opened, "recoveries_without_progress": since, "productive_watermark": completed, "reason": reason})
        return RecoveryStormReport(opened, since, completed, reason)

    def dispatch_allowed(self, state: ProjectState, task: Task) -> tuple[bool, str]:
        if bool((state.metadata.get("recovery_storm_breaker") or {}).get("open")):
            return False, "global_recovery_storm_breaker_open"
        if int(task.attempts) >= max(1, int(task.max_attempts)):
            return False, "task_attempt_budget_exhausted"
        tmeta = task.metadata.get(self.KEY) or {}
        if int(tmeta.get("count", 0) or 0) >= self.per_task_trip:
            return False, "task_recovery_budget_exhausted"
        return True, "ok"
