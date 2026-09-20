from __future__ import annotations

import os
import pathlib
import sys

ROOT = pathlib.Path(os.environ.get("CEO_GATE_ROOT", "/tmp/ceo-dev307-autonomy-invariants")).resolve()
sys.path.insert(0, str(ROOT))

from ceo_core.models import ProjectState, Task, TaskStatus
from ceo_core.quality_gate import QualityGateVerdict
from ceo_core.scheduler import ContinuousScheduler
from ceo_core.self_correction import SelfCorrectionEngine


class DoneFuture:
    def done(self):
        return True

    def cancelled(self):
        return False

    def exception(self):
        return None


def test_finished_future_invariant() -> dict:
    state = ProjectState(goal="field reproduction")
    state.metadata["worker_recoveries"] = 0
    task = Task(
        title="Research & discovery · work unit 5",
        status=TaskStatus.RUNNING,
        attempts=1,
        max_attempts=3,
        worker_id="worker-field",
        provider_name="gemini-interactions",
    )
    state.tasks[task.id] = task
    state.root_task_ids.append(task.id)

    scheduler = ContinuousScheduler.__new__(ContinuousScheduler)
    scheduler.state = state
    scheduler._active = {task.id: DoneFuture()}
    scheduler._active_provider = {task.id: "gemini-interactions"}

    scheduler._collect_finished()

    assert task.id not in scheduler._active
    assert task.status == TaskStatus.RETRY
    assert task.worker_id is None
    assert task.metadata.get("provider_stage") == "future_finished_state_reconciled"
    assert task.metadata.get("worker_future_state_reconciled_v1", {}).get("recovery_budget_consumed") is False
    assert int(state.metadata.get("worker_recoveries", 0) or 0) == 0
    rows = state.metadata.get("worker_future_state_reconciliations_v1") or []
    assert len(rows) == 1

    # Idempotence: another collector pass cannot create another recovery/reconciliation.
    scheduler._collect_finished()
    assert len(state.metadata.get("worker_future_state_reconciliations_v1") or []) == 1
    assert int(state.metadata.get("worker_recoveries", 0) or 0) == 0
    return {
        "status": task.status.value,
        "reconciliations": len(rows),
        "worker_recoveries": int(state.metadata.get("worker_recoveries", 0) or 0),
    }


def verdict(task: Task, signature: str) -> QualityGateVerdict:
    return QualityGateVerdict(
        accepted=False,
        score=0.20,
        threshold=0.55,
        reasons=["quality_below_threshold"],
        action="retry_or_repair",
        retry_safe=True,
        signature=signature,
    )


def test_quality_lineage_bound() -> dict:
    state = ProjectState(goal="quality loop reproduction")
    state.metadata["max_inline_quality_corrections"] = 1
    state.metadata["max_quality_repair_generations"] = 2
    engine = SelfCorrectionEngine()

    root = Task(title="Research & discovery · work unit 5", attempts=0, max_attempts=3)
    state.tasks[root.id] = root
    state.root_task_ids.append(root.id)

    e1 = engine.recover_quality_failure(state, root, verdict(root, "sig-task-0-a"))
    assert e1["action"] == "inline_retry"
    assert root.status == TaskStatus.RETRY

    e2 = engine.recover_quality_failure(state, root, verdict(root, "sig-task-0-b"))
    assert e2["action"] == "replacement_task"
    r1 = state.tasks[e2["replacement_task_id"]]
    assert int(r1.metadata.get("repair_generation", 0)) == 1

    e3 = engine.recover_quality_failure(state, r1, verdict(r1, "sig-task-1"))
    assert e3["action"] == "replacement_task"
    r2 = state.tasks[e3["replacement_task_id"]]
    assert int(r2.metadata.get("repair_generation", 0)) == 2

    count_before = len(state.tasks)
    e4 = engine.recover_quality_failure(state, r2, verdict(r2, "sig-task-2"))
    assert e4["action"] == "quality_repair_exhausted"
    assert r2.status == TaskStatus.FAILED
    assert r2.metadata.get("quality_repair_exhausted_v1")
    assert len(state.tasks) == count_before, "exhausted lineage spawned another repair task"

    repair_tasks = [t for t in state.tasks.values() if t.metadata.get("self_correction_replacement_of")]
    assert len(repair_tasks) == 2
    return {
        "root_action_1": e1["action"],
        "root_action_2": e2["action"],
        "generation_1_action": e3["action"],
        "generation_2_action": e4["action"],
        "repair_tasks": len(repair_tasks),
        "final_status": r2.status.value,
    }


def main() -> int:
    a = test_finished_future_invariant()
    b = test_quality_lineage_bound()
    print("DEV307_INVARIANT_REGRESSION_PASS")
    print({"finished_future": a, "quality_lineage": b})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
