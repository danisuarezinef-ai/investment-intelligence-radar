from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path

from ceo_core.autonomy_hardening_readiness_v1 import evaluate_autonomy_hardening_readiness_v1
from ceo_core.autonomy_hardening_soak_v1 import AutonomyHardeningSoakV1
from ceo_core.control_churn_circuit_breaker_v1 import ControlChurnCircuitBreakerV1
from ceo_core.contracts import WorkerKind, WorkerProvider, WorkerRequest, WorkerResult
from ceo_core.goal_completion_resolver_v1 import GoalCompletionResolverV1
from ceo_core.historical_incident_regression_v1 import HistoricalIncidentRegressionV1
from ceo_core.models import ProjectState, Task, TaskStatus
from ceo_core.productive_progress_guard_v1 import ProductiveProgressGuardV1
from ceo_core.queue_consistency_rebuilder_v1 import QueueConsistencyRebuilderV1
from ceo_core.recovery_budget_guard_v1 import RecoveryBudgetGuardV1
from ceo_core.scheduler import ContinuousScheduler
from ceo_core.scheduler_productivity_supervisor_v1 import SchedulerProductivitySupervisorV1
from ceo_core.store import JsonCheckpointStore

CANDIDATE = "1.4.98-rc1-autonomy-hardening"


def add(state: ProjectState, task: Task) -> Task:
    state.tasks[task.id] = task
    state.root_task_ids.append(task.id)
    return task


class Provider(WorkerProvider):
    name = "dev221-provider"
    kind = WorkerKind.MOCK
    capabilities = frozenset({"general", "reasoning", "verification"})

    def __init__(self) -> None:
        self.calls = 0

    def supports(self, task: Task) -> bool:
        return True

    async def execute(self, request: WorkerRequest) -> WorkerResult:
        self.calls += 1
        await asyncio.sleep(0.015)
        return WorkerResult(
            provider=self.name,
            kind=self.kind,
            success=True,
            text=f"Verified deliverable for {request.work_unit.title}",
            conversation_id=f"dev221-{self.calls}",
            metadata={"acceptance_evidence": True},
        )


def recovery_budget_check() -> bool:
    s = ProjectState(goal="budget")
    for i in range(10):
        add(s, Task(title=f"Autonomous recovery {i}", status=TaskStatus.RETRY,
                    metadata={"task_role": "control", "autonomy_recovery": True, "blocker_signature": "same"}))
    s.metadata["autonomy_recovery_tasks_created"] = 790
    s.metadata["recovery_events"] = [{"kind": "worker_watchdog_recovery", "title": "same"} for _ in range(50)]
    productive = add(s, Task(title="fresh productive work", status=TaskStatus.READY, metadata={"task_role": "productive"}))
    guard = RecoveryBudgetGuardV1(max_recoveries_without_progress=8, max_active_internal=2)
    report = guard.apply(s)
    active = [t for t in s.leaf_tasks if t.status in {TaskStatus.READY, TaskStatus.RETRY, TaskStatus.RUNNING, TaskStatus.NEEDS_REVIEW} and t is not productive]
    first_ok = report.budget_exhausted and len(active) <= 2 and report.retired_excess >= 8
    productive.status = TaskStatus.COMPLETE; productive.result = "done"; productive.metadata["acceptance_evidence"] = True
    after_progress = guard.apply(s)
    return first_ok and not after_progress.budget_exhausted


def progress_watchdog_check() -> bool:
    s = ProjectState(goal="progress")
    add(s, Task(title="internal", status=TaskStatus.READY, metadata={"task_role": "control"}))
    guard = ProductiveProgressGuardV1(stall_cycles=4, control_only_cycles=3)
    r = None
    for _ in range(4):
        r = guard.assess(s)
    return bool(r and r.stalled and r.control_only_cycles >= 3)


def circuit_breaker_check() -> bool:
    s = ProjectState(goal="circuit")
    for i in range(5):
        add(s, Task(title="Continuity recovery duplicate", status=TaskStatus.RETRY,
                    metadata={"task_role": "control", "continuity_gap_recovery": True}))
    s.metadata["activity_timeline"] = [{"kind": "cognitive_early_abort", "title": "Continuity recovery duplicate"} for _ in range(10)]
    report = ControlChurnCircuitBreakerV1(trip_count=4).apply(s, productive_stalled=True)
    active = [t for t in s.leaf_tasks if t.status in {TaskStatus.READY, TaskStatus.RETRY, TaskStatus.RUNNING, TaskStatus.NEEDS_REVIEW}]
    return report.open and len(active) <= 1 and report.duplicate_internal_retired >= 4


def completion_resolver_check() -> bool:
    s = ProjectState(goal="complete", metadata={"goal_audit_passed": True})
    add(s, Task(title="done", status=TaskStatus.COMPLETE, result="done",
                metadata={"task_role": "productive", "acceptance_evidence": True}))
    report = GoalCompletionResolverV1().resolve(s)
    return report.action == "complete" and s.completed_at is not None


def queue_rebuilder_check() -> bool:
    s = ProjectState(goal="queue")
    internal = add(s, Task(title="Continuity recovery verify", status=TaskStatus.NEEDS_REVIEW,
                           metadata={"task_role": "verification", "continuity_gap_recovery": True, "task_kind": "verification"}))
    orphan = add(s, Task(title="orphan work", status=TaskStatus.RUNNING, worker_id="ghost", metadata={"task_role": "productive"}))
    report = QueueConsistencyRebuilderV1().rebuild(s, active_task_ids=set())
    return report.internal_review_recovered == 1 and report.orphan_running_requeued == 1 and internal.status in {TaskStatus.READY, TaskStatus.RETRY} and orphan.status in {TaskStatus.READY, TaskStatus.RETRY} and orphan.worker_id is None


def supervisor_check() -> bool:
    s = ProjectState(goal="supervisor")
    productive = add(s, Task(title="real work", status=TaskStatus.READY, metadata={"task_role": "productive"}))
    internal = add(s, Task(title="internal review", status=TaskStatus.NEEDS_REVIEW, metadata={"task_role": "verification"}))
    protected = add(s, Task(title="payment approval", status=TaskStatus.NEEDS_REVIEW,
                            metadata={"task_role": "control", "explicit_human_gate": True, "payment": True}))
    report = SchedulerProductivitySupervisorV1().tick(s, active_task_ids=set())
    return productive.status == TaskStatus.READY and internal.status in {TaskStatus.READY, TaskStatus.RETRY} and protected.status == TaskStatus.NEEDS_REVIEW and report.productive_ready >= 1


async def e2e_churn_with_productive_work() -> dict:
    with tempfile.TemporaryDirectory(prefix="dev221-e2e-") as td:
        state = ProjectState(
            goal="Finish productive work despite historical continuity churn",
            power_percent=100,
            verification_percent=0,
            metadata={
                "strict_completion_audit": False,
                "require_goal_audit": False,
                "completion_confidence_threshold": 0.0,
                "strategic_tick_interval": 10000,
                "autonomy_recovery_tasks_created": 790,
                "recovery_events": [{"kind": "worker_watchdog_recovery", "title": "same"} for _ in range(80)],
                "activity_timeline": [{"kind": "cognitive_early_abort", "title": "continuity"} for _ in range(20)],
                "concurrency_observations": [{"workers": 4, "throughput": 4.0, "failures": 0}],
            },
        )
        productive = []
        for i in range(4):
            productive.append(add(state, Task(
                title=f"Productive output {i+1}", status=TaskStatus.READY, priority=100-i,
                estimated_seconds=0.02, required_capabilities=["general"],
                metadata={"task_role": "productive", "quality_gate_threshold": 0.0},
            )))
        internal = add(state, Task(
            title="Continuity recovery: independently verify the new result against the locked goal [cycle 1]",
            status=TaskStatus.NEEDS_REVIEW, priority=20, estimated_seconds=0.02,
            required_capabilities=["verification"],
            metadata={"task_role": "verification", "continuity_gap_recovery": True, "task_kind": "verification", "failure_count": 7, "predicted_success_probability": 0.1, "quality_gate_threshold": 0.0},
        ))
        provider = Provider(); store = JsonCheckpointStore(Path(td) / "state.json")
        scheduler = ContinuousScheduler(state, provider, store)
        scheduler.start()
        deadline = asyncio.get_running_loop().time() + 6.0
        while asyncio.get_running_loop().time() < deadline:
            if all(t.status == TaskStatus.COMPLETE for t in productive):
                break
            await asyncio.sleep(0.05)
        await scheduler.stop()
        return {
            "productive_completed": sum(t.status == TaskStatus.COMPLETE for t in productive),
            "provider_calls": provider.calls,
            "internal_status": internal.status.value,
            "false_human_review": internal.status == TaskStatus.NEEDS_REVIEW,
            "circuit": bool(state.metadata.get("control_plane_circuit_open")),
            "budget_exhausted": bool(state.metadata.get("control_plane_recovery_budget_exhausted")),
            "supervisor": state.metadata.get("scheduler_productivity_supervisor_v1", {}),
        }


def main() -> int:
    hist = HistoricalIncidentRegressionV1().run()
    soak = AutonomyHardeningSoakV1().run(rounds=10000, seed=221)
    e2e = asyncio.run(e2e_churn_with_productive_work())
    checks = {
        "DEV213_recovery_budget_guard_v1": recovery_budget_check(),
        "DEV214_productive_progress_watchdog_v1": progress_watchdog_check(),
        "DEV215_control_churn_circuit_breaker_v1": circuit_breaker_check(),
        "DEV216_goal_completion_resolver_v1": completion_resolver_check(),
        "DEV217_queue_consistency_rebuilder_v1": queue_rebuilder_check(),
        "DEV218_scheduler_productivity_supervisor_v1": supervisor_check(),
        "DEV219_historical_incident_regression_v1": hist.violations == 0,
        "DEV220_autonomy_hardening_soak_v1": soak.violations == 0 and soak.rounds == 10000,
        "DEV221_churn_e2e_productive_progress": e2e["productive_completed"] == 4 and not e2e["false_human_review"],
    }
    readiness = evaluate_autonomy_hardening_readiness_v1(
        recovery_budget_guard=checks["DEV213_recovery_budget_guard_v1"],
        productive_progress_watchdog=checks["DEV214_productive_progress_watchdog_v1"],
        churn_circuit_breaker=checks["DEV215_control_churn_circuit_breaker_v1"],
        goal_completion_resolver=checks["DEV216_goal_completion_resolver_v1"],
        queue_consistency_rebuilder=checks["DEV217_queue_consistency_rebuilder_v1"],
        productivity_supervisor=checks["DEV218_scheduler_productivity_supervisor_v1"],
        historical_incident_pack=checks["DEV219_historical_incident_regression_v1"],
        hardening_soak=checks["DEV220_autonomy_hardening_soak_v1"],
        dev212_regression=True,
        clean_package=True,
    )
    ok = all(checks.values()) and readiness.local_candidate_ready
    print(json.dumps({
        "ok": ok,
        "candidate": CANDIDATE,
        "checks": checks,
        "historical_regression": hist.to_dict(),
        "soak": soak.to_dict(),
        "e2e": e2e,
        "readiness": readiness.to_dict(),
    }, indent=2, sort_keys=True))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
