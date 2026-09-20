from __future__ import annotations

import asyncio
import os
import pathlib
import sys

ROOT = pathlib.Path(os.environ["CEO_DEV307_BUILD_ROOT"])
sys.path.insert(0, str(ROOT))

from ceo_core.models import ProjectState, Task, TaskStatus
from ceo_core.scheduler import ContinuousScheduler, RELIABILITY_EPOCH, _apply_reliability_epoch_migration
from ceo_core.self_correction import SelfCorrectionEngine
from ceo_core.quality_gate import QualityGateVerdict
from ceo_core.blocked_safe_state_v1 import mark_blocked_safe

EXPECTED_EPOCH = "dev307-autonomy-runtime-integrity-v1"


class DoneFuture:
    def __init__(self, exc=None, cancelled=False):
        self._exc = exc
        self._cancelled = cancelled
    def done(self):
        return True
    def cancelled(self):
        return self._cancelled
    def exception(self):
        return self._exc


def fake_scheduler(state: ProjectState, task: Task, future: DoneFuture):
    s = object.__new__(ContinuousScheduler)
    s.state = state
    s._active = {task.id: future}
    s._active_provider = {task.id: task.provider_name or "gemini-interactions"}
    return s


def test_finished_future_never_leaves_running() -> None:
    state = ProjectState(goal="field orphan regression")
    state.metadata["worker_recoveries"] = 38
    task = Task(title="Research & discovery · work unit 5", status=TaskStatus.RUNNING)
    task.provider_name = "gemini-interactions"
    task.attempts = 1
    task.max_attempts = 3
    state.tasks[task.id] = task
    state.root_task_ids.append(task.id)

    sched = fake_scheduler(state, task, DoneFuture())
    ContinuousScheduler._collect_finished(sched)

    assert task.status == TaskStatus.RETRY, task.status
    assert task.id not in sched._active
    assert int(state.metadata.get("worker_recoveries", 0)) == 38
    row = task.metadata.get("worker_terminal_normalization_v1") or {}
    assert row.get("recovery_budget_consumed") is False, row
    assert row.get("outcome") == "completed_without_terminal_state", row
    print("DEV307_FINISHED_FUTURE_NORMALIZATION_PASS")


def test_exception_future_bounded_without_worker_recovery() -> None:
    state = ProjectState(goal="exception future")
    state.metadata["worker_recoveries"] = 0
    task = Task(title="Execution", status=TaskStatus.RUNNING)
    task.attempts = 1
    task.max_attempts = 3
    state.tasks[task.id] = task
    state.root_task_ids.append(task.id)

    for n in range(3):
        task.status = TaskStatus.RUNNING
        sched = fake_scheduler(state, task, DoneFuture(RuntimeError("worker exited")))
        ContinuousScheduler._collect_finished(sched)

    assert task.status == TaskStatus.FAILED, task.status
    assert int(state.metadata.get("worker_recoveries", 0)) == 0
    assert task.metadata.get("worker_terminal_normalization_count") == 3
    print("DEV307_BOUNDED_WORKER_HANDOFF_PASS")


def test_field_migration_releases_only_proven_orphan_block() -> None:
    state = ProjectState(goal="resume field gate")
    state.metadata["worker_recoveries"] = 38
    state.metadata["worker_recovery_history"] = []
    state.metadata["reliability_epoch_v1"] = {"epoch": "dev305-endgame-closure-v1"}

    orphan = Task(title="Research orphan", status=TaskStatus.BLOCKED)
    orphan.attempts = orphan.max_attempts
    mark_blocked_safe(orphan, "worker_recovery_budget_exhausted", source="worker_recovery_supervisor")
    state.tasks[orphan.id] = orphan
    state.root_task_ids.append(orphan.id)
    state.metadata["worker_recovery_history"].append({
        "task_id": orphan.id,
        "reason": "orphan_running_without_live_future",
        "action": "retry",
    })

    legitimate = Task(title="Legitimate safety block", status=TaskStatus.BLOCKED)
    mark_blocked_safe(legitimate, "destructive_action_requires_approval", source="safety")
    state.tasks[legitimate.id] = legitimate
    state.root_task_ids.append(legitimate.id)

    report = _apply_reliability_epoch_migration(state)
    assert RELIABILITY_EPOCH == EXPECTED_EPOCH
    assert orphan.id in report["released_false_orphan_task_ids"], report
    assert orphan.status == TaskStatus.RETRY
    assert not orphan.metadata.get("blocked_safe")
    assert "recovery_storm_guard_v1" not in orphan.metadata
    assert legitimate.status == TaskStatus.BLOCKED
    assert legitimate.metadata.get("blocked_safe") is True
    assert int((state.metadata.get("productive_truth_v2") or {}).get("recoveries_at_watermark", -1)) == 38
    print("DEV307_SELECTIVE_FIELD_MIGRATION_PASS")


def test_quality_repair_lineage_is_bounded() -> None:
    state = ProjectState(goal="quality loop")
    state.metadata["max_inline_quality_corrections"] = 1
    state.metadata["max_quality_repair_generations"] = 2
    engine = SelfCorrectionEngine()

    task = Task(title="Research", status=TaskStatus.COMPLETE)
    task.max_attempts = 5
    state.tasks[task.id] = task
    state.root_task_ids.append(task.id)

    def verdict(t: Task):
        return QualityGateVerdict(
            accepted=False,
            score=0.2,
            threshold=0.55,
            reasons=["quality_below_threshold"],
            action="retry_or_repair",
            retry_safe=True,
            signature=f"quality-{t.id}",
        )

    # Generation 0: one inline retry, then replacement generation 1.
    out1 = engine.recover_quality_failure(state, task, verdict(task))
    assert out1["action"] == "inline_retry"
    task.status = TaskStatus.COMPLETE
    out2 = engine.recover_quality_failure(state, task, verdict(task))
    assert out2["action"] == "replacement_task", out2
    r1 = state.tasks[out2["replacement_task_id"]]
    assert int(r1.metadata.get("repair_generation", 0)) == 1

    # Generation 1: one inline retry, then replacement generation 2.
    r1.status = TaskStatus.COMPLETE
    out3 = engine.recover_quality_failure(state, r1, verdict(r1))
    assert out3["action"] == "inline_retry", out3
    r1.status = TaskStatus.COMPLETE
    out4 = engine.recover_quality_failure(state, r1, verdict(r1))
    assert out4["action"] == "replacement_task", out4
    r2 = state.tasks[out4["replacement_task_id"]]
    assert int(r2.metadata.get("repair_generation", 0)) == 2

    # Generation 2 may retry inline once, but can never spawn generation 3.
    r2.status = TaskStatus.COMPLETE
    out5 = engine.recover_quality_failure(state, r2, verdict(r2))
    assert out5["action"] == "inline_retry", out5
    r2.status = TaskStatus.COMPLETE
    out6 = engine.recover_quality_failure(state, r2, verdict(r2))
    assert out6["action"] == "bounded_quality_failure", out6
    assert r2.status == TaskStatus.FAILED
    replacements = [t for t in state.tasks.values() if t.metadata.get("self_correction_replacement_of")]
    assert len(replacements) == 2, len(replacements)
    assert max(int(t.metadata.get("repair_generation", 0) or 0) for t in replacements) == 2
    print("DEV307_BOUNDED_QUALITY_LINEAGE_PASS")


def main() -> None:
    assert RELIABILITY_EPOCH == EXPECTED_EPOCH, RELIABILITY_EPOCH
    test_finished_future_never_leaves_running()
    test_exception_future_bounded_without_worker_recovery()
    test_field_migration_releases_only_proven_orphan_block()
    test_quality_repair_lineage_is_bounded()
    print("DEV307_AUTONOMY_RUNTIME_INTEGRITY_PASS")


if __name__ == "__main__":
    main()
