from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .models import ProjectState, Task, TaskStatus
from .progress_tracker import StableProgressTracker
from .scheduler_productivity_supervisor_v1 import SchedulerProductivitySupervisorV1


@dataclass(slots=True)
class HistoricalIncidentRegressionResult:
    false_internal_review: bool
    recovery_790_contained: bool
    false_99_rebased: bool
    ready_zero_worker_repairable: bool
    orphan_running_recovered: bool
    goal_closure_resolved: bool
    protected_gate_preserved: bool
    violations: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _add(state: ProjectState, task: Task) -> Task:
    state.tasks[task.id] = task
    state.root_task_ids.append(task.id)
    return task


class HistoricalIncidentRegressionV1:
    """Executable memories of the physical Windows failures observed before DEV221."""

    def run(self) -> HistoricalIncidentRegressionResult:
        violations = 0
        supervisor = SchedulerProductivitySupervisorV1()

        # Incident A: internal continuity task stranded in NEEDS_REVIEW.
        a = ProjectState(goal="A")
        internal = _add(a, Task(
            title="Continuity recovery: independently verify the new result against the locked goal [cycle 1]",
            status=TaskStatus.NEEDS_REVIEW,
            metadata={"continuity_gap_recovery": True, "task_kind": "verification", "task_role": "verification"},
        ))
        supervisor.tick(a, active_task_ids=set())
        false_internal_review = internal.status in {TaskStatus.READY, TaskStatus.RETRY}
        violations += 0 if false_internal_review else 1

        # Incident B: hundreds of control recoveries with no productive work.
        b = ProjectState(goal="B")
        for i in range(12):
            _add(b, Task(title=f"Autonomous recovery {i}", status=TaskStatus.RETRY,
                         metadata={"autonomy_recovery": True, "task_role": "control", "blocker_signature": "same"}))
        b.metadata["autonomy_recovery_tasks_created"] = 790
        b.metadata["recovery_events"] = [
            {"kind": "worker_watchdog_recovery", "title": "same"} for _ in range(200)
        ]
        rep_b = supervisor.tick(b, active_task_ids=set())
        active_internal = [t for t in b.leaf_tasks if t.status in {TaskStatus.READY, TaskStatus.RETRY, TaskStatus.RUNNING, TaskStatus.NEEDS_REVIEW}]
        recovery_790_contained = rep_b.recovery_budget_exhausted and len(active_internal) <= 2 and bool(b.metadata.get("suppress_new_internal_recovery"))
        violations += 0 if recovery_790_contained else 1

        # Incident C: legacy 99% display created by control tasks while productive work is at 0%.
        c = ProjectState(goal="C")
        _add(c, Task(title="real work", status=TaskStatus.READY, metadata={"task_role": "productive"}))
        for i in range(20):
            _add(c, Task(title=f"control {i}", status=TaskStatus.COMPLETE, metadata={"task_role": "control"}))
        c.metadata["stable_progress_v1"] = {"display_progress": 99.0}
        snap = StableProgressTracker().snapshot(c, persist=True)
        false_99_rebased = snap["display_progress"] < 50.0 and snap["productive_completed"] == 0
        violations += 0 if false_99_rebased else 1

        # Incident D/E: runnable productive work with no in-memory worker + orphan RUNNING.
        d = ProjectState(goal="D")
        ready = _add(d, Task(title="productive ready", status=TaskStatus.READY, metadata={"task_role": "productive"}))
        orphan = _add(d, Task(title="productive orphan", status=TaskStatus.RUNNING, worker_id="ghost", metadata={"task_role": "productive"}))
        rep_d = supervisor.tick(d, active_task_ids=set())
        ready_zero_worker_repairable = ready.status == TaskStatus.READY and rep_d.productive_ready >= 1
        orphan_running_recovered = orphan.status in {TaskStatus.READY, TaskStatus.RETRY} and orphan.worker_id is None
        violations += 0 if ready_zero_worker_repairable else 1
        violations += 0 if orphan_running_recovered else 1

        # Incident F: goal already audited PASS must not remain stuck at 99 forever.
        e = ProjectState(goal="E", metadata={"goal_audit_passed": True})
        _add(e, Task(title="done", status=TaskStatus.COMPLETE, result="done", metadata={"task_role": "productive", "acceptance_evidence": True}))
        rep_e = supervisor.tick(e, active_task_ids=set())
        goal_closure_resolved = e.completed_at is not None and rep_e.completion_action == "complete"
        violations += 0 if goal_closure_resolved else 1

        # Incident G: protected human operation must remain NEEDS_REVIEW.
        f = ProjectState(goal="F")
        protected = _add(f, Task(title="publish release", status=TaskStatus.NEEDS_REVIEW,
                                 metadata={"task_role": "control", "external_action": True, "explicit_human_gate": True}))
        supervisor.tick(f, active_task_ids=set())
        protected_gate_preserved = protected.status == TaskStatus.NEEDS_REVIEW
        violations += 0 if protected_gate_preserved else 1

        return HistoricalIncidentRegressionResult(
            false_internal_review=false_internal_review,
            recovery_790_contained=recovery_790_contained,
            false_99_rebased=false_99_rebased,
            ready_zero_worker_repairable=ready_zero_worker_repairable,
            orphan_running_recovered=orphan_running_recovered,
            goal_closure_resolved=goal_closure_resolved,
            protected_gate_preserved=protected_gate_preserved,
            violations=violations,
        )
