from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone

from .continuity_policy import is_internal_continuity_task, protected_human_gate
from .models import ProjectState, TaskStatus
from .blocked_safe_state_v1 import preserve_blocked_safe
from .task_roles_v2 import is_internal, is_productive

_DONE = {
    TaskStatus.COMPLETE,
    TaskStatus.PARTIAL_COMPLETE,
    TaskStatus.COMPLETE_WITH_UNCERTAINTY,
    TaskStatus.SUPERSEDED,
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(slots=True)
class ReconcileReport:
    internal_reviews_recovered: int = 0
    orphan_running_recovered: int = 0
    dependency_unblocked: int = 0
    stale_stall_cleared: int = 0
    productive_open: int = 0
    executable: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


class SchedulerStateReconcilerV1:
    """Idempotent scheduler-state repair for persisted/restarted projects.

    It never approves genuine human/safety gates. It only repairs states that the
    runtime can prove are internal scheduler/control artifacts.
    """

    KEY = "scheduler_reconciler_v1"

    def reconcile(self, state: ProjectState, *, active_task_ids: set[str] | None = None) -> ReconcileReport:
        active = set(active_task_ids or ())
        report = ReconcileReport()
        now = _now()

        # 1) Internal continuity/recovery work must not wait for the operator unless
        # a structured protected gate is present.
        for task in state.leaf_tasks:
            if preserve_blocked_safe(task, source="scheduler_reconciler:review"):
                continue
            if task.status != TaskStatus.NEEDS_REVIEW:
                continue
            if not (is_internal(task, state) or is_internal_continuity_task(state, task)):
                continue
            if protected_human_gate(task):
                continue
            task.status = TaskStatus.RETRY
            task.max_attempts = max(int(task.max_attempts), int(task.attempts) + 2)
            task.metadata.pop("requires_user", None)
            task.metadata.pop("decision_id", None)
            task.metadata["scheduler_internal_review_recovered_at"] = now
            task.metadata["next_instruction"] = (
                "Internal scheduler/control work: continue autonomously. Escalate only a genuine "
                "protected human-only action; otherwise finish or create concrete executable work."
            )
            report.internal_reviews_recovered += 1

        # 2) A durable RUNNING state without an in-memory worker is a restart orphan.
        # Requeue it rather than pretending a worker still exists.
        for task in state.leaf_tasks:
            if preserve_blocked_safe(task, source="scheduler_reconciler:orphan"):
                continue
            if task.status != TaskStatus.RUNNING or task.id in active:
                continue
            task.status = TaskStatus.RETRY
            task.worker_id = None
            task.metadata["orphan_running_recovered_at"] = now
            task.metadata["interrupted_by_shutdown"] = task.metadata.get("interrupted_by_shutdown") or now
            task.metadata["provider_stage"] = "restart_requeued"
            report.orphan_running_recovered += 1

        # 3) Fast dependency propagation. The normal graph refresh will run after
        # this too; doing it here makes persisted states self-heal in one cycle.
        ts = datetime.now(timezone.utc).timestamp()
        for task in state.leaf_tasks:
            if preserve_blocked_safe(task, source="scheduler_reconciler:deps"):
                continue
            if task.status not in {TaskStatus.WAITING, TaskStatus.BLOCKED, TaskStatus.RETRY}:
                continue
            if task.metadata.get("paused"):
                continue
            retry_after = float(task.metadata.get("retry_after_ts", 0) or 0)
            if retry_after > ts:
                continue
            deps_done = all(dep in state.tasks and state.tasks[dep].status in _DONE for dep in task.dependencies)
            if deps_done:
                if task.status != TaskStatus.READY:
                    task.status = TaskStatus.READY
                    task.metadata.pop("dependency_blockers", None)
                    task.metadata["dependency_unblocked_at"] = now
                    report.dependency_unblocked += 1

        productive_open = [
            t for t in state.leaf_tasks
            if is_productive(t, state) and t.status not in _DONE and t.status != TaskStatus.FAILED
        ]
        executable = [
            t for t in state.leaf_tasks
            if t.status in {TaskStatus.READY, TaskStatus.RETRY, TaskStatus.RUNNING}
        ]
        report.productive_open = len(productive_open)
        report.executable = len(executable)

        # A stale bounded-stall marker is historical once executable work exists.
        if executable and state.metadata.pop("autonomy_stalled", None) is not None:
            report.stale_stall_cleared += 1
            state.metadata["autonomy_stall_cleared_at"] = now
            state.metadata["autonomy_stall_cycles"] = 0

        meta = state.metadata.setdefault(self.KEY, {})
        totals = meta.setdefault("totals", {})
        for key, value in report.to_dict().items():
            if key in {"productive_open", "executable"}:
                continue
            totals[key] = int(totals.get(key, 0)) + int(value)
        meta["last"] = {**report.to_dict(), "ts": now}
        return report
