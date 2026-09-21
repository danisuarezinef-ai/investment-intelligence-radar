from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .models import Task, TaskStatus


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def is_blocked_safe(task: Task) -> bool:
    """Return True when generic scheduler repair must not reopen this task.

    BLOCKED is historically overloaded in CEO: it can mean either a transient
    dependency wait or a fail-closed recovery stop.  `blocked_safe` is the durable
    latch that distinguishes the latter.  Generic readiness/reconciliation code
    must preserve this latch until an explicit strategy/replan operation releases
    it.
    """
    return bool(task.metadata.get("blocked_safe") or task.metadata.get("manual_release_required"))


def preserve_blocked_safe(task: Task, *, source: str | None = None) -> bool:
    """Enforce the fail-closed latch and return whether it was active."""
    if not is_blocked_safe(task):
        return False
    task.status = TaskStatus.BLOCKED
    task.worker_id = None
    task.metadata["auto_reopen_allowed"] = False
    if source:
        task.metadata["blocked_safe_preserved_by"] = str(source)
        task.metadata["blocked_safe_preserved_at"] = _now()
    return True


def mark_blocked_safe(task: Task, reason: str, *, source: str = "recovery_guard") -> None:
    """Latch a task into a persistent fail-closed state."""
    task.status = TaskStatus.BLOCKED
    task.worker_id = None
    task.metadata["blocked_safe"] = True
    task.metadata["blocked_safe_reason"] = str(reason)
    task.metadata["blocked_safe_source"] = str(source)
    task.metadata["blocked_safe_at"] = _now()
    task.metadata["auto_reopen_allowed"] = False
    task.metadata["retry_after_ts"] = 0


def release_blocked_safe(task: Task, *, reason: str, strategy: str) -> dict[str, Any]:
    """Explicitly release the latch after a real strategy change.

    This is intentionally never called by generic dependency/readiness repair.
    Callers must name the applied strategy so release is auditable.
    """
    if not is_blocked_safe(task):
        return {"released": False, "reason": "not_blocked_safe"}
    previous = str(task.metadata.get("blocked_safe_reason") or "")
    hist = task.metadata.setdefault("blocked_safe_release_history", [])
    hist.append({"ts": _now(), "previous_reason": previous, "release_reason": str(reason), "strategy": str(strategy)})
    del hist[:-20]
    task.metadata["blocked_safe"] = False
    task.metadata["manual_release_required"] = False
    task.metadata["auto_reopen_allowed"] = True
    task.metadata["blocked_safe_released_at"] = _now()
    task.metadata["blocked_safe_release_reason"] = str(reason)
    task.metadata["blocked_safe_release_strategy"] = str(strategy)
    task.status = TaskStatus.RETRY
    return {"released": True, "previous_reason": previous, "strategy": str(strategy)}
