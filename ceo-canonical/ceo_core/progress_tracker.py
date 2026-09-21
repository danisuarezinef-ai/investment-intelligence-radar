from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .models import ProjectState, Task, TaskStatus
from .task_roles_v2 import is_control, is_productive, is_verification

TERMINAL_OK = {
    TaskStatus.COMPLETE,
    TaskStatus.PARTIAL_COMPLETE,
    TaskStatus.COMPLETE_WITH_UNCERTAINTY,
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def is_control_plane(task: Task) -> bool:
    return is_control(task) or is_verification(task)



class StableProgressTracker:
    """Operator-facing progress that does not move backwards when CEO discovers work.

    `ProjectState.progress` is a ratio over the *current* leaf task set. In a continuous
    system the denominator grows whenever follow-up tasks are discovered, so that ratio
    can legitimately fall from 100 to 95 even though no completed work was lost. That is
    useful internally but confusing as an operator progress indicator.

    This tracker exposes both:
      * batch_progress: instantaneous ratio over known non-control work (may change), and
      * display_progress: a persisted high-water mark (never decreases).

    Completion still requires the real completion gate; the high-water mark is capped at
    99 until the project is genuinely completed.
    """

    KEY = "stable_progress_v2"

    def snapshot(self, state: ProjectState, *, persist: bool = True) -> dict[str, Any]:
        leaves = [t for t in state.leaf_tasks if t.status != TaskStatus.SUPERSEDED]
        domain = [t for t in leaves if is_productive(t, state)]
        control = [t for t in leaves if not is_productive(t, state)]
        domain_done = [t for t in domain if t.status in TERMINAL_OK]
        control_done = [t for t in control if t.status in TERMINAL_OK]
        domain_running = [t for t in domain if t.status == TaskStatus.RUNNING]
        domain_pending = [t for t in domain if t.status not in TERMINAL_OK and t.status != TaskStatus.SUPERSEDED]

        batch_progress = round(100.0 * len(domain_done) / len(domain), 1) if domain else 0.0
        meta = state.metadata.setdefault(self.KEY, {}) if persist else dict(state.metadata.get(self.KEY) or {})
        previous = float(meta.get("display_progress", 0.0) or 0.0)
        completed = bool(state.completed_at is not None and state.metadata.get("goal_audit_passed"))
        candidate = 100.0 if completed else min(99.0, batch_progress)

        # DEV195 migration: DEV15-DEV194 could persist a 99% high-water mark produced
        # by control/recovery leaves. Rebase once onto productive work rather than
        # preserving a visibly false percentage forever. After the v2 baseline is
        # established, productive progress remains monotonic again.
        migrated = bool(meta.get("v2_productive_baseline"))
        if not migrated:
            legacy_v1 = state.metadata.get("stable_progress_v1") or {}
            legacy_display = float(legacy_v1.get("display_progress", state.progress) or 0.0)
            inflated = (not completed) and legacy_display >= 95.0 and batch_progress + 15.0 < legacy_display
            display = candidate if inflated else max(candidate, min(99.0, legacy_display))
            meta["v2_productive_baseline"] = True
            meta["legacy_rebased"] = bool(inflated)
            meta["legacy_display_before_rebase"] = round(legacy_display, 1)
        else:
            display = max(previous, candidate)

        latest_ts = None
        latest_task = None
        for task in domain_done:
            ts = task.completed_at or task.started_at or task.created_at
            if latest_ts is None or ts > latest_ts:
                latest_ts = ts
                latest_task = task

        if persist:
            meta.update({
                "version": 2,
                "initialized": True,
                "display_progress": round(display, 1),
                "batch_progress": batch_progress,
                "productive_completed": len(domain_done),
                "productive_total_known": len(domain),
                "control_completed": len(control_done),
                "updated_at": _now(),
            })
            if latest_ts is not None:
                meta["last_productive_progress_at"] = latest_ts.isoformat()
                meta["last_productive_task_id"] = latest_task.id if latest_task else None
                meta["last_productive_task_title"] = latest_task.title if latest_task else None

        return {
            "display_progress": round(display, 1),
            "batch_progress": batch_progress,
            "productive_completed": len(domain_done),
            "productive_total_known": len(domain),
            "productive_running": len(domain_running),
            "productive_pending": len(domain_pending),
            "control_completed": len(control_done),
            "control_running": sum(t.status == TaskStatus.RUNNING for t in control),
            "control_pending": sum(t.status not in TERMINAL_OK and t.status != TaskStatus.SUPERSEDED for t in control),
            "last_productive_progress_at": (latest_ts.isoformat() if latest_ts else meta.get("last_productive_progress_at")),
            "last_productive_task_id": latest_task.id if latest_task else meta.get("last_productive_task_id"),
            "last_productive_task_title": latest_task.title if latest_task else meta.get("last_productive_task_title"),
            "completed": completed,
        }
