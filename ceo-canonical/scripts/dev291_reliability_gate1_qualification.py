from __future__ import annotations

import asyncio
from ceo_core.models import ProjectState, Task, TaskStatus
from ceo_core.operational_resilience import WorkerRecoverySupervisor
from ceo_core.recovery_storm_guard_v1 import RecoveryStormGuardV1
from ceo_core.goal_lock_local_provider_v1 import GoalLockLocalProviderV1
from ceo_core.contracts import GoalContract, WorkerRequest, WorkUnit


def test_per_task_bound():
    state = ProjectState(project_name="gate1", goal="test")
    task = Task(title="ordinary task", status=TaskStatus.RUNNING, max_attempts=50, provider_name="dead-provider")
    state.tasks[task.id] = task
    state.root_task_ids.append(task.id)
    sup = WorkerRecoverySupervisor()
    actions=[]
    for i in range(12):
        task.status = TaskStatus.RUNNING
        task.attempts = i + 1
        row = sup.reconcile(state, active={}, providers={})
        if row["recovered"]:
            actions.append(row["recovered"][-1]["action"])
        if task.status == TaskStatus.BLOCKED:
            break
    assert task.status == TaskStatus.BLOCKED, (task.status, actions)
    assert task.metadata.get("blocked_safe") is True
    assert int(task.metadata["recovery_storm_guard_v1"]["count"]) <= 6
    assert any(a in {"retry_changed_strategy", "retry_strategy_change_requested"} for a in actions), actions
    return {"actions": actions, "count": task.metadata["recovery_storm_guard_v1"]["count"]}


def test_attempt_budget():
    state = ProjectState(project_name="gate1", goal="test")
    task = Task(title="budget", status=TaskStatus.RUNNING, max_attempts=3, attempts=3)
    state.tasks[task.id] = task
    sup = WorkerRecoverySupervisor()
    row=sup.reconcile(state, active={}, providers={})
    assert task.status == TaskStatus.BLOCKED
    assert row["recovered"][0]["action"] == "blocked_safe"
    return row["recovered"][0]


def test_global_storm_breaker():
    state = ProjectState(project_name="gate1", goal="test")
    state.metadata["worker_recoveries"] = 0
    guard = RecoveryStormGuardV1(global_trip=12)
    guard.assess(state)  # establish the post-upgrade recovery epoch
    state.metadata["worker_recoveries"] = 12
    rep = guard.assess(state)
    assert rep.open
    assert state.metadata.get("suppress_new_internal_recovery") is True
    assert state.metadata.get("operator_productivity_state") == "BLOQUEADO"
    t=Task(title="should not dispatch", status=TaskStatus.READY)
    allowed, reason = guard.dispatch_allowed(state,t)
    assert not allowed and reason == "global_recovery_storm_breaker_open"
    return rep.to_dict()


async def test_local_goal_lock():
    provider=GoalLockLocalProviderV1()
    task=Task(title="Clarify & lock goal", metadata={"local_fallback_kind":"goal_lock"})
    assert provider.supports(task)
    goal=GoalContract(objective="Repair reliability", definition="Repair reliability", constraints=["offline-safe"], completion_criteria=["bounded recovery"], deliverables=["candidate"])
    req=WorkerRequest(project_id="p", work_unit=WorkUnit.from_task(task), goal=goal, context={})
    res=await provider.execute(req)
    assert res.success and res.metadata.get("network_used") is False
    return {"provider":res.provider,"success":res.success}


def main():
    results={
      "per_task_bound":test_per_task_bound(),
      "attempt_budget":test_attempt_budget(),
      "global_storm_breaker":test_global_storm_breaker(),
      "local_goal_lock":asyncio.run(test_local_goal_lock()),
    }
    print(results)

if __name__ == "__main__":
    main()
