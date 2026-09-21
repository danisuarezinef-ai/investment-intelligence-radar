from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .models import ProjectState, TaskStatus


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class RealWorkQueue:
    """Thin operational view over CEO's existing persistent task graph.

    The scheduler remains the execution engine.  This class gives the Goal Engine
    a stable, explicit 'real work queue' surface without duplicating task state.
    """

    VERSION = 1

    def initialize(self, state: ProjectState) -> dict[str, Any]:
        meta = state.metadata.setdefault("real_work_queue_v1", {})
        meta.setdefault("version", self.VERSION)
        meta.setdefault("created_at", _now())
        meta["last_seen_at"] = _now()
        # Persistent platform invariants.  These are policy declarations; concrete
        # spend/promotion actions still pass through their existing human gates.
        meta.setdefault("safety", {
            "automatic_spending": False,
            "automatic_candidate_promotion": False,
            "destructive_actions_require_gate": True,
        })
        return self.snapshot(state)

    def snapshot(self, state: ProjectState, *, limit: int = 100) -> dict[str, Any]:
        tasks = list(state.tasks.values())
        order = {
            TaskStatus.RUNNING: 0,
            TaskStatus.READY: 1,
            TaskStatus.RETRY: 2,
            TaskStatus.WAITING: 3,
            TaskStatus.NEEDS_REVIEW: 4,
            TaskStatus.BLOCKED: 5,
            TaskStatus.FAILED: 6,
            TaskStatus.PARTIAL_COMPLETE: 7,
            TaskStatus.COMPLETE_WITH_UNCERTAINTY: 8,
            TaskStatus.COMPLETE: 9,
            TaskStatus.SUPERSEDED: 10,
        }
        tasks.sort(key=lambda t: (order.get(t.status, 99), -int(t.priority), t.created_at))
        rows = [
            {
                "id": t.id,
                "title": t.title,
                "status": t.status.value,
                "priority": t.priority,
                "dependencies": list(t.dependencies),
                "parent_id": t.parent_id,
                "provider": t.provider_name,
                "attempts": t.attempts,
                "max_attempts": t.max_attempts,
                "estimated_seconds": t.estimated_seconds,
            }
            for t in tasks[: max(1, int(limit))]
        ]
        counts: dict[str, int] = {}
        for t in tasks:
            counts[t.status.value] = counts.get(t.status.value, 0) + 1
        return {
            "version": self.VERSION,
            "objective": state.goal,
            "project_id": state.id,
            "progress": state.progress,
            "paused": state.paused,
            "autonomy_enabled": state.autonomy_enabled,
            "counts": counts,
            "queue": rows,
            "safety": dict((state.metadata.get("real_work_queue_v1") or {}).get("safety") or {
                "automatic_spending": False,
                "automatic_candidate_promotion": False,
                "destructive_actions_require_gate": True,
            }),
        }
