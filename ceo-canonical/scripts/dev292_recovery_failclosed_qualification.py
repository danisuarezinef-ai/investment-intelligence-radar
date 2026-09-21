from __future__ import annotations

import asyncio
import tempfile
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from datetime import datetime, timedelta, timezone

from ceo_core.blocked_safe_state_v1 import mark_blocked_safe
from ceo_core.contracts import WorkerKind, WorkerProvider, WorkerRequest, WorkerResult
from ceo_core.decomposer import TaskDecomposer
from ceo_core.dependency_manager import DependencyManager
from ceo_core.directors_v2 import HierarchicalDirectorV2
from ceo_core.graph import TaskGraph
from ceo_core.models import ProjectState, Task, TaskStatus
from ceo_core.operational_resilience import ResumeCoordinator
from ceo_core.queue_consistency_rebuilder_v1 import QueueConsistencyRebuilderV1
from ceo_core.recovery_storm_guard_v1 import RecoveryStormGuardV1
from ceo_core.scheduler import ContinuousScheduler
from ceo_core.scheduler_reconciler_v1 import SchedulerStateReconcilerV1
from ceo_core.autonomous_loop import AutonomousProjectLoop
from ceo_core.productivity_stall_replanner_v2 import ProductivityStallReplannerV2
from ceo_core.dynamic_task_tree import DynamicTaskTreeManager
from ceo_core.store import JsonCheckpointStore


class CountingProvider(WorkerProvider):
    name = "only-provider"
    kind = WorkerKind.MOCK
    capabilities = frozenset({"general"})
    def __init__(self):
        self.calls = 0
    async def execute(self, request: WorkerRequest) -> WorkerResult:
        self.calls += 1
        return WorkerResult(provider=self.name, kind=self.kind, success=True, text="CEO_RESULT: complete\nuseful")


class PendingFuture:
    def __init__(self): self.cancelled = False
    def done(self): return False
    def cancel(self): self.cancelled = True


def make_state() -> tuple[ProjectState, Task]:
    state = ProjectState(project_name="dev292", goal="reliability")
    task = Task(title="productive", status=TaskStatus.BLOCKED, required_capabilities=["general"], metadata={"task_role":"productive"})
    state.tasks[task.id] = task
    state.root_task_ids = [task.id]
    return state, task


def test_blocked_safe_inviolable() -> dict:
    state, task = make_state()
    mark_blocked_safe(task, "budget_exhausted", source="test")

    SchedulerStateReconcilerV1().reconcile(state)
    assert task.status == TaskStatus.BLOCKED and task.metadata.get("blocked_safe")
    QueueConsistencyRebuilderV1().rebuild(state)
    assert task.status == TaskStatus.BLOCKED
    TaskGraph().refresh(state)
    assert task.status == TaskStatus.BLOCKED
    DependencyManager().reconcile(state)
    assert task.status == TaskStatus.BLOCKED
    TaskDecomposer().refresh_readiness(state)
    assert task.status == TaskStatus.BLOCKED
    ResumeCoordinator().prepare(state, source="dev292")
    assert task.status == TaskStatus.BLOCKED
    HierarchicalDirectorV2().build(state)
    director_id = next(iter(state.metadata.get("director_v2") or {}), None)
    if director_id:
        HierarchicalDirectorV2().local_replan(state, director_id)
    assert task.status == TaskStatus.BLOCKED
    return {"status": task.status.value, "blocked_safe": bool(task.metadata.get("blocked_safe"))}


def test_breaker_atomic_close() -> dict:
    state = ProjectState(project_name="breaker", goal="breaker")
    guard = RecoveryStormGuardV1(global_trip=12)
    guard.assess(state)
    state.metadata["worker_recoveries"] = 12
    opened = guard.assess(state)
    assert opened.open
    assert state.metadata.get("recovery_storm_breaker", {}).get("open")
    assert state.metadata.get("suppress_new_internal_recovery") is True
    done = Task(title="useful", status=TaskStatus.COMPLETE, result="evidence", metadata={"task_role":"productive"})
    state.tasks[done.id] = done; state.root_task_ids.append(done.id)
    closed = guard.assess(state)
    assert not closed.open
    assert "recovery_storm_breaker" not in state.metadata
    assert "suppress_new_internal_recovery" not in state.metadata
    assert state.metadata.get("operator_productivity_state") == "ACTIVO"
    return {"opened": opened.open, "closed": not closed.open, "state": state.metadata.get("operator_productivity_state")}


def test_restart_5_of_6_then_latch() -> dict:
    with tempfile.TemporaryDirectory() as td:
        store = JsonCheckpointStore(Path(td)/"state.json")
        state = ProjectState(project_name="restart", goal="restart")
        task = Task(title="timeout task", status=TaskStatus.RUNNING, max_attempts=50, attempts=5, provider_name="p", metadata={"task_role":"productive"})
        task.metadata["recovery_storm_guard_v1"]={"count":5,"last_fingerprint":"x","repeat_count":1}
        state.tasks[task.id]=task; state.root_task_ids=[task.id]
        store.save(state)
        loaded=store.load(); assert loaded is not None
        lt=loaded.tasks[task.id]
        # Six total recovery events are terminal for the work unit.
        guard=RecoveryStormGuardV1(per_task_trip=6)
        # Reset signature to force count update without relying on old test fingerprint.
        decision=guard.record_task_recovery(lt, reason="worker_watchdog_timeout", provider="p")
        assert decision["count"] == 6 and decision["exhausted"]
        mark_blocked_safe(lt,"worker_recovery_budget_exhausted",source="dev292_restart")
        store.save(loaded)
        loaded2=store.load(); assert loaded2 is not None
        ResumeCoordinator().prepare(loaded2,source="dev292_restart")
        SchedulerStateReconcilerV1().reconcile(loaded2)
        TaskGraph().refresh(loaded2)
        final=loaded2.tasks[task.id]
        assert final.status == TaskStatus.BLOCKED and final.metadata.get("blocked_safe")
        assert int(final.metadata["recovery_storm_guard_v1"]["count"]) == 6
        return {"count":6,"status":final.status.value,"preserved":True}


def test_breaker_persists_restart() -> dict:
    with tempfile.TemporaryDirectory() as td:
        store=JsonCheckpointStore(Path(td)/"state.json")
        state=ProjectState(project_name="breaker-restart",goal="breaker")
        t=Task(title="x",status=TaskStatus.READY,metadata={"task_role":"productive"})
        state.tasks[t.id]=t; state.root_task_ids=[t.id]
        guard=RecoveryStormGuardV1(global_trip=12)
        guard.assess(state); state.metadata["worker_recoveries"]=12; assert guard.assess(state).open
        store.save(state); loaded=store.load(); assert loaded is not None
        allowed,reason=guard.dispatch_allowed(loaded,loaded.tasks[t.id])
        assert not allowed and reason=="global_recovery_storm_breaker_open"
        return {"dispatch_allowed":allowed,"reason":reason}


async def test_scheduler_rejects_fake_strategy_change() -> dict:
    provider=CountingProvider()
    with tempfile.TemporaryDirectory() as td:
        state=ProjectState(project_name="scheduler",goal="scheduler")
        t=Task(title="productive",status=TaskStatus.READY,required_capabilities=["general"],metadata={"task_role":"productive","strategy_change_requested":True,"strategy_change_from":provider.name,"strategy_change_applied":False})
        state.tasks[t.id]=t; state.root_task_ids=[t.id]
        scheduler=ContinuousScheduler(state,provider,JsonCheckpointStore(Path(td)/"state.json"))
        await scheduler._run_task(t)
        assert provider.calls == 0
        assert t.status == TaskStatus.BLOCKED and t.metadata.get("blocked_safe")
        assert t.metadata.get("blocked_safe_reason") == "strategy_change_unavailable"
        return {"provider_calls":provider.calls,"status":t.status.value,"reason":t.metadata.get("blocked_safe_reason")}


async def test_watchdog_to_strategy_gate() -> dict:
    provider=CountingProvider()
    with tempfile.TemporaryDirectory() as td:
        state=ProjectState(project_name="watchdog",goal="watchdog")
        t=Task(title="productive",status=TaskStatus.RUNNING,required_capabilities=["general"],provider_name=provider.name,max_attempts=50,metadata={"task_role":"productive","provider_timeout_seconds":1})
        state.tasks[t.id]=t; state.root_task_ids=[t.id]
        scheduler=ContinuousScheduler(state,provider,JsonCheckpointStore(Path(td)/"state.json"))
        # Two identical watchdog incidents request a real strategy change.
        for _ in range(2):
            t.status=TaskStatus.RUNNING
            t.started_at=datetime.now(timezone.utc)-timedelta(seconds=120)
            fut=PendingFuture(); scheduler._active={t.id:fut}; scheduler._active_provider={t.id:provider.name}
            scheduler._recover_live_workers()
            scheduler._active={}; scheduler._active_provider={}
        assert t.metadata.get("strategy_change_requested") is True
        assert t.metadata.get("strategy_change_applied") is False
        t.status=TaskStatus.READY
        await scheduler._run_task(t)
        assert provider.calls == 0
        assert t.status == TaskStatus.BLOCKED and t.metadata.get("blocked_safe")
        return {"recoveries":state.metadata.get("worker_recoveries"),"provider_calls":provider.calls,"status":t.status.value}



def test_no_recovery_ladder_for_blocked_safe() -> dict:
    state, task = make_state()
    mark_blocked_safe(task, "bounded_failure", source="dev292")
    before=len(state.tasks)
    row=AutonomousProjectLoop().ensure_progress(state)
    assert row.get("status") == "bounded_stall", row
    assert len(state.tasks) == before
    rep=ProductivityStallReplannerV2().repair(state)
    assert rep.requeued == 0 and rep.replacements == 0
    DynamicTaskTreeManager().maintain(state)
    assert task.status == TaskStatus.BLOCKED and task.metadata.get("blocked_safe")
    return {"autonomous_status":row.get("status"),"tasks":len(state.tasks),"requeued":rep.requeued,"replacements":rep.replacements}

def main():
    results={
        "blocked_safe_inviolable":test_blocked_safe_inviolable(),
        "breaker_atomic_close":test_breaker_atomic_close(),
        "restart_5_of_6":test_restart_5_of_6_then_latch(),
        "breaker_restart":test_breaker_persists_restart(),
        "strategy_change_gate":asyncio.run(test_scheduler_rejects_fake_strategy_change()),
        "watchdog_pipeline":asyncio.run(test_watchdog_to_strategy_gate()),
        "no_recovery_ladder_for_blocked_safe":test_no_recovery_ladder_for_blocked_safe(),
    }
    print(results)

if __name__ == "__main__": main()
