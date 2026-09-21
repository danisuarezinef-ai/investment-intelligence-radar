from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .models import ProjectState, Task, TaskStatus


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class DegradedOperationManager:
    """Keeps safe local work moving while unavailable capabilities are quarantined."""

    KEY = "degraded_operation_v1"
    LOCAL_KINDS = {"local", "filesystem", "analysis", "code_review", "batch_tests", "summarize", "planning"}

    def enter(self, state: ProjectState, *, reason: str, unavailable: list[str]) -> dict[str, Any]:
        row = state.metadata.setdefault(self.KEY, {})
        row.update({"active": True, "reason": str(reason), "unavailable": sorted(set(str(x) for x in unavailable)), "entered_at": _now(), "updated_at": _now()})
        row.setdefault("events", []).append({"ts": _now(), "event": "enter", "reason": str(reason), "unavailable": row["unavailable"]})
        del row["events"][:-200]
        return dict(row)

    def exit(self, state: ProjectState, *, reason: str = "capability_restored") -> dict[str, Any]:
        row = state.metadata.setdefault(self.KEY, {})
        row.update({"active": False, "reason": str(reason), "unavailable": [], "updated_at": _now(), "exited_at": _now()})
        row.setdefault("events", []).append({"ts": _now(), "event": "exit", "reason": reason})
        del row["events"][:-200]
        return dict(row)

    def classify(self, state: ProjectState, task: Task) -> dict[str, Any]:
        row = state.metadata.get(self.KEY, {}) or {}
        if not row.get("active"):
            return {"runnable": True, "reason": "normal_mode"}
        unavailable = set(row.get("unavailable") or [])
        required = {str(x).lower() for x in task.required_capabilities}
        kind = str(task.metadata.get("task_kind") or "").lower()
        if any(cap in unavailable for cap in required):
            return {"runnable": False, "reason": "required_capability_unavailable"}
        if any(bool(task.metadata.get(k)) for k in ("destructive", "irreversible", "spending", "publication", "external_side_effect")):
            return {"runnable": False, "reason": "external_effect_deferred_in_degraded_mode"}
        if kind in self.LOCAL_KINDS or not required:
            return {"runnable": True, "reason": "safe_local_work"}
        return {"runnable": False, "reason": "degraded_unknown_capability"}

    def reconcile(self, state: ProjectState) -> dict[str, Any]:
        runnable = deferred = 0
        for task in state.leaf_tasks:
            if task.status not in {TaskStatus.READY, TaskStatus.RETRY, TaskStatus.WAITING, TaskStatus.BLOCKED}:
                continue
            verdict = self.classify(state, task)
            if verdict["runnable"]:
                runnable += 1
                if task.metadata.pop("degraded_deferred", None):
                    if task.status == TaskStatus.BLOCKED:
                        task.status = TaskStatus.READY
            else:
                deferred += 1
                task.metadata["degraded_deferred"] = verdict["reason"]
                if task.status in {TaskStatus.READY, TaskStatus.RETRY, TaskStatus.WAITING}:
                    task.status = TaskStatus.BLOCKED
        summary = {"active": bool((state.metadata.get(self.KEY) or {}).get("active")), "runnable": runnable, "deferred": deferred, "at": _now()}
        state.metadata.setdefault(self.KEY, {})["last_reconcile"] = summary
        return summary
