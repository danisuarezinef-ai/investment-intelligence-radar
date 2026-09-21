from __future__ import annotations

import asyncio
import json
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ceo_core.autonomous_loop import AutonomousProjectLoop
from ceo_core.completion import CompletionEngine
from ceo_core.contracts import WorkerKind, WorkerProvider, WorkerRequest, WorkerResult
from ceo_core.goal_completion_gate import GoalCompletionGate
from ceo_core.liveness import ProductiveProgressWatchdog
from ceo_core.models import Decision, ProjectState, Task, TaskStatus
from ceo_core.operational_resilience import ResumeCoordinator
from ceo_core.progress_tracker import StableProgressTracker
from ceo_core.quality_gate import AutomaticQualityGate
from ceo_core.release_readiness_v16 import evaluate_release_readiness_v16
from ceo_core.scheduler import ContinuousScheduler
from ceo_core.scheduler_reconciler_v1 import SchedulerStateReconcilerV1
from ceo_core.soak_guard_v11 import SoakGuardV11
from ceo_core.store import JsonCheckpointStore
from ceo_core.task_roles_v2 import TaskRole, is_productive, task_role


class DeterministicProvider(WorkerProvider):
    name = "dev201-deterministic"
    kind = WorkerKind.MOCK
    capabilities = frozenset({"general", "reasoning", "verification"})

    def supports(self, task: Task) -> bool:
        return True

    async def execute(self, request: WorkerRequest) -> WorkerResult:
        return WorkerResult(
            provider=self.name,
            kind=self.kind,
            success=True,
            text=f"Substantive result for {request.work_unit.title}",
            conversation_id=f"dev201-{request.work_unit.id}",
        )


def add(state: ProjectState, task: Task) -> Task:
    state.tasks[task.id] = task
    state.root_task_ids.append(task.id)
    return task


def role_checks() -> bool:
    s = ProjectState(goal="roles")
    p = Task(title="Implement feature")
    c = Task(title="Goal continuity audit #1", metadata={"goal_continuity_audit": True, "control_plane_atomic": True})
    x = Task(title="Continuity recovery: execute", metadata={"continuity_gap_recovery": True, "task_kind": "general", "productive_recovery_work": True})
    v = Task(title="Independent verification 1", metadata={"continuity_gap_recovery": True, "task_kind": "verification"})
    h = Task(title="Publish", metadata={"explicit_human_gate": True, "external_action": True})
    return (
        task_role(p, s) == TaskRole.PRODUCTIVE
        and task_role(c, s) == TaskRole.CONTROL
        and task_role(x, s) == TaskRole.PRODUCTIVE
        and task_role(v, s) == TaskRole.VERIFICATION
        and task_role(h, s) == TaskRole.HUMAN_GATE
    )


def quality_checks() -> bool:
    gate = AutomaticQualityGate()
    s = ProjectState(goal="quality")
    c = Task(title="control", status=TaskStatus.COMPLETE, result="control result", metadata={"control_plane_atomic": True})
    c.acceptance_criteria = ["internal protocol completes"]
    c_ok = gate.evaluate(s, c, quality=0.01).accepted
    empty = Task(title="empty control", status=TaskStatus.COMPLETE, metadata={"control_plane_atomic": True})
    empty_ok = gate.evaluate(s, empty, quality=1.0).accepted
    p = Task(title="productive", status=TaskStatus.COMPLETE, result="domain result")
    p_ok = gate.evaluate(s, p, quality=0.01).accepted
    return c_ok and not empty_ok and not p_ok


def completion_checks() -> bool:
    engine = CompletionEngine()
    s = ProjectState(goal="completion")
    prod = add(s, Task(title="real work", status=TaskStatus.COMPLETE, result="done", quality_score=0.9))
    internal = add(s, Task(title="Continuity recovery: verify", status=TaskStatus.NEEDS_REVIEW, metadata={"continuity_gap_recovery": True, "task_kind": "verification"}))
    d = Decision(title="internal", description="internal", options=["continue"], metadata={"source_task_id": internal.id})
    s.decisions[d.id] = d
    a = engine.assess(s)
    if not a.complete:
        return False
    external = add(s, Task(title="pay", status=TaskStatus.NEEDS_REVIEW, metadata={"explicit_human_gate": True, "external_action": True}))
    d2 = Decision(title="real human", description="external", options=["yes", "no"], metadata={"source_task_id": external.id, "external_action": True})
    s.decisions[d2.id] = d2
    b = engine.assess(s)
    return (not b.complete) and "open_decisions" in b.blockers


def progress_checks() -> bool:
    s = ProjectState(goal="progress")
    for i in range(4):
        t = Task(title=f"domain-{i}", status=TaskStatus.COMPLETE if i == 0 else TaskStatus.WAITING)
        if i == 0:
            t.result = "done"
        add(s, t)
    for i in range(12):
        add(s, Task(title=f"control-{i}", status=TaskStatus.COMPLETE, result="ok", metadata={"control_plane_atomic": True}))
    s.metadata["stable_progress_v1"] = {"initialized": True, "display_progress": 99.0}
    snap = StableProgressTracker().snapshot(s, persist=True)
    return snap["batch_progress"] == 25.0 and snap["display_progress"] == 25.0 and bool(s.metadata["stable_progress_v2"].get("legacy_rebased"))


def reconciler_checks() -> bool:
    s = ProjectState(goal="reconcile")
    dep = add(s, Task(title="dep", status=TaskStatus.COMPLETE, result="done"))
    internal = add(s, Task(title="Continuity recovery: verify", status=TaskStatus.NEEDS_REVIEW, metadata={"continuity_gap_recovery": True, "task_kind": "verification"}))
    human = add(s, Task(title="external publish", status=TaskStatus.NEEDS_REVIEW, metadata={"explicit_human_gate": True, "external_action": True}))
    orphan = add(s, Task(title="orphan", status=TaskStatus.RUNNING))
    waiting = add(s, Task(title="waiting", status=TaskStatus.BLOCKED, dependencies=[dep.id]))
    s.metadata["autonomy_stalled"] = {"reason": "historical"}
    r = SchedulerStateReconcilerV1().reconcile(s, active_task_ids=set())
    return (
        internal.status in {TaskStatus.RETRY, TaskStatus.READY}
        and human.status == TaskStatus.NEEDS_REVIEW
        and orphan.status in {TaskStatus.RETRY, TaskStatus.READY}
        and waiting.status == TaskStatus.READY
        and r.internal_reviews_recovered == 1
        and r.orphan_running_recovered == 1
        and r.dependency_unblocked >= 1
        and "autonomy_stalled" not in s.metadata
    )


def restart_checks() -> bool:
    s = ProjectState(goal="restart")
    safe = add(s, Task(title="safe running", status=TaskStatus.RUNNING))
    external = add(s, Task(title="external running", status=TaskStatus.RUNNING, metadata={"external_action": True}))
    dep = add(s, Task(title="done dep", status=TaskStatus.COMPLETE, result="done"))
    blocked = add(s, Task(title="blocked", status=TaskStatus.BLOCKED, dependencies=[dep.id]))
    report = ResumeCoordinator().prepare(s, source="dev197-test")
    return (
        safe.status == TaskStatus.RETRY
        and external.status == TaskStatus.NEEDS_REVIEW
        and blocked.status == TaskStatus.READY
        and report.recovered_running == 1
        and report.ambiguous_external_effects == 1
        and report.dependency_repairs == 1
    )


def liveness_checks() -> bool:
    old = datetime.now(timezone.utc) - timedelta(seconds=10)
    s = ProjectState(goal="live", started_at=old)
    add(s, Task(title="control", status=TaskStatus.RUNNING, metadata={"control_plane_atomic": True}))
    w = ProductiveProgressWatchdog(stall_after_seconds=1)
    a = w.assess(s, now=datetime.now(timezone.utc), persist=False)
    if not (a.stalled and a.status == "control_only_stall"):
        return False
    add(s, Task(title="productive", status=TaskStatus.RUNNING))
    b = w.assess(s, now=datetime.now(timezone.utc), persist=False)
    return (not b.stalled) and b.status == "productive_running"


def goal_audit_checks() -> bool:
    loop = AutonomousProjectLoop()
    # No productive success -> never create final audit.
    s0 = ProjectState(goal="audit0", metadata={"require_goal_audit": True, "goal_audit_passed": False})
    add(s0, Task(title="not done", status=TaskStatus.SUPERSEDED))
    row0 = loop.ensure_progress(s0)
    if row0.get("status") == "goal_audit_created":
        return False
    # Real productive completion -> continuity audit becomes legitimate.
    s1 = ProjectState(goal="audit1", metadata={"require_goal_audit": True, "goal_audit_passed": False})
    done = add(s1, Task(title="real done", status=TaskStatus.COMPLETE, result="real evidence", quality_score=0.9))
    row1 = loop.ensure_progress(s1)
    if row1.get("status") != "goal_audit_created":
        return False
    # Pure control wrapper cannot be used as completion evidence.
    c = add(s1, Task(title="Autonomous recovery · fresh worker", status=TaskStatus.COMPLETE, result="control", metadata={"autonomy_recovery": True, "control_plane_atomic": True}))
    verdict = GoalCompletionGate().evaluate(s1, evidence_refs=[c.id, done.id])
    return c.id not in verdict.evidence_refs and done.id in verdict.evidence_refs


def chain_checks() -> bool:
    s = ProjectState(goal="chain")
    audit = add(s, Task(title="Goal continuity audit #1", status=TaskStatus.SUPERSEDED, metadata={"goal_continuity_audit": True, "control_plane_atomic": True}))
    map_t = add(s, Task(title="Continuity recovery: map", status=TaskStatus.WAITING, dependencies=[audit.id], metadata={"continuity_gap_recovery": True, "task_kind": "reasoning", "task_role": "control"}))
    exec_t = add(s, Task(title="Continuity recovery: execute", status=TaskStatus.WAITING, dependencies=[map_t.id], metadata={"continuity_gap_recovery": True, "task_kind": "general", "task_role": "productive", "productive_recovery_work": True}))
    verify = add(s, Task(title="Continuity recovery: verify", status=TaskStatus.WAITING, dependencies=[exec_t.id], metadata={"continuity_gap_recovery": True, "task_kind": "verification", "task_role": "verification"}))
    rec = SchedulerStateReconcilerV1()
    rec.reconcile(s, active_task_ids=set())
    if map_t.status != TaskStatus.READY:
        return False
    map_t.status = TaskStatus.COMPLETE; map_t.result = "map"
    rec.reconcile(s, active_task_ids=set())
    if exec_t.status != TaskStatus.READY:
        return False
    exec_t.status = TaskStatus.COMPLETE; exec_t.result = "productive evidence"
    rec.reconcile(s, active_task_ids=set())
    return verify.status == TaskStatus.READY and is_productive(exec_t, s) and not is_productive(verify, s)


async def scheduler_e2e_check() -> bool:
    with tempfile.TemporaryDirectory(prefix="dev201-e2e-") as td:
        state = ProjectState(
            goal="Complete one deterministic productive task",
            project_name="DEV201 E2E",
            verification_percent=0,
            power_percent=30,
            metadata={
                "strict_completion_audit": False,
                "require_goal_audit": False,
                "completion_confidence_threshold": 0.0,
                "strategic_tick_interval": 1000,
            },
        )
        task = Task(
            title="Deterministic productive work",
            status=TaskStatus.READY,
            required_capabilities=["general"],
            estimated_seconds=0.01,
            metadata={"quality_gate_threshold": 0.0},
        )
        add(state, task)
        store = JsonCheckpointStore(Path(td) / "state.json")
        scheduler = ContinuousScheduler(state, DeterministicProvider(), store)
        scheduler.start()
        deadline = asyncio.get_running_loop().time() + 4.0
        while asyncio.get_running_loop().time() < deadline:
            if task.status == TaskStatus.COMPLETE:
                break
            await asyncio.sleep(0.05)
        await scheduler.stop()
        loaded = store.load()
        return bool(
            task.status == TaskStatus.COMPLETE
            and (task.result or "").startswith("Substantive result")
            and loaded is not None
            and loaded.tasks[task.id].status == TaskStatus.COMPLETE
        )


def main() -> int:
    checks: dict[str, object] = {}
    checks["DEV192_task_role_unification"] = role_checks()
    checks["DEV193_control_completion_semantics"] = quality_checks() and completion_checks()
    checks["DEV194_scheduler_state_reconciler"] = reconciler_checks()
    checks["DEV195_productive_progress_v2"] = progress_checks()
    checks["DEV196_dependency_closure"] = chain_checks()
    checks["DEV197_restart_recovery"] = restart_checks()
    checks["DEV198_productive_liveness_guard"] = liveness_checks()
    checks["DEV199_goal_audit_timing"] = goal_audit_checks()
    soak = SoakGuardV11().run(rounds=5000, seed=201)
    checks["DEV200_soak_guard_v11"] = soak.violations == 0 and soak.accepted == soak.rounds
    checks["DEV201_scheduler_e2e"] = asyncio.run(scheduler_e2e_check())

    readiness = evaluate_release_readiness_v16(
        dev189_regression=True,
        task_role_unification=bool(checks["DEV192_task_role_unification"]),
        scheduler_reconciliation=bool(checks["DEV194_scheduler_state_reconciler"]),
        productive_progress_v2=bool(checks["DEV195_productive_progress_v2"]),
        restart_recovery=bool(checks["DEV197_restart_recovery"]),
        liveness_guard=bool(checks["DEV198_productive_liveness_guard"]),
        goal_audit_timing=bool(checks["DEV199_goal_audit_timing"]),
        mission_soak=bool(checks["DEV200_soak_guard_v11"]),
        clean_package=True,
    )
    checks["DEV201_release_readiness_v16"] = readiness.local_candidate_ready

    ok = all(bool(v) for v in checks.values())
    result = {
        "ok": ok,
        "candidate": "1.4.78-rc1-autonomy-stability-consolidation",
        "checks": checks,
        "soak": soak.to_dict(),
        "readiness": readiness.to_dict(),
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
