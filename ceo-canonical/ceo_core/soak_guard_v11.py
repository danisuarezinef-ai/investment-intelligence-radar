from __future__ import annotations

import random
from dataclasses import asdict, dataclass

from .models import ProjectState, Task, TaskStatus
from .scheduler_reconciler_v1 import SchedulerStateReconcilerV1
from .task_roles_v2 import is_internal, is_productive

_DONE = {
    TaskStatus.COMPLETE,
    TaskStatus.PARTIAL_COMPLETE,
    TaskStatus.COMPLETE_WITH_UNCERTAINTY,
    TaskStatus.SUPERSEDED,
}


@dataclass(slots=True)
class SoakV11Result:
    rounds: int
    accepted: int
    violations: int
    internal_reviews_recovered: int
    orphan_running_recovered: int
    dependency_unblocked: int
    protected_gates_preserved: int

    def to_dict(self) -> dict:
        return asdict(self)


def _task(title: str, status: TaskStatus, **metadata) -> Task:
    return Task(title=title, status=status, metadata=metadata)


class SoakGuardV11:
    """Adversarial state-reconciliation soak for DEV192-DEV201."""

    def run(self, rounds: int = 5000, seed: int = 201) -> SoakV11Result:
        rng = random.Random(seed)
        reconciler = SchedulerStateReconcilerV1()
        accepted = violations = 0
        totals = {
            "internal_reviews_recovered": 0,
            "orphan_running_recovered": 0,
            "dependency_unblocked": 0,
            "protected_gates_preserved": 0,
        }
        for i in range(rounds):
            state = ProjectState(goal=f"soak-{i}", project_name="DEV200 soak")

            base = _task("domain base", TaskStatus.COMPLETE)
            base.result = "evidence"
            state.tasks[base.id] = base
            state.root_task_ids.append(base.id)

            # Internal false human review: must recover automatically.
            internal = _task(
                "Continuity recovery: independently verify",
                TaskStatus.NEEDS_REVIEW,
                continuity_gap_recovery=True,
                task_kind="verification",
            )
            state.tasks[internal.id] = internal
            state.root_task_ids.append(internal.id)

            # Genuine protected human gate: must never be auto-recovered.
            protected = _task(
                "Publish release",
                TaskStatus.NEEDS_REVIEW,
                explicit_human_gate=True,
                external_action=True,
                requires_explicit_human=True,
            )
            state.tasks[protected.id] = protected
            state.root_task_ids.append(protected.id)

            # Persisted RUNNING with no active worker.
            orphan = _task("orphan running", TaskStatus.RUNNING)
            state.tasks[orphan.id] = orphan
            state.root_task_ids.append(orphan.id)

            # Dependency should become READY in one reconciliation pass.
            dependent = _task("dependent productive", rng.choice([TaskStatus.WAITING, TaskStatus.BLOCKED, TaskStatus.RETRY]))
            dependent.dependencies = [base.id]
            state.tasks[dependent.id] = dependent
            state.root_task_ids.append(dependent.id)

            report = reconciler.reconcile(state, active_task_ids=set())
            totals["internal_reviews_recovered"] += report.internal_reviews_recovered
            totals["orphan_running_recovered"] += report.orphan_running_recovered
            totals["dependency_unblocked"] += report.dependency_unblocked

            ok = True
            if internal.status not in {TaskStatus.RETRY, TaskStatus.READY}:
                ok = False
            if protected.status != TaskStatus.NEEDS_REVIEW:
                ok = False
            else:
                totals["protected_gates_preserved"] += 1
            if orphan.status not in {TaskStatus.RETRY, TaskStatus.READY}:
                ok = False
            if dependent.status != TaskStatus.READY:
                ok = False
            if not is_internal(internal, state) or is_productive(internal, state):
                ok = False
            if not is_productive(dependent, state):
                ok = False

            if ok:
                accepted += 1
            else:
                violations += 1

        return SoakV11Result(
            rounds=rounds,
            accepted=accepted,
            violations=violations,
            **totals,
        )
