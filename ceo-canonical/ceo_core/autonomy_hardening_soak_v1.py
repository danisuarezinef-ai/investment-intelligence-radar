from __future__ import annotations

import random
from dataclasses import asdict, dataclass
from typing import Any

from .models import ProjectState, Task, TaskStatus
from .scheduler_productivity_supervisor_v1 import SchedulerProductivitySupervisorV1


@dataclass(slots=True)
class AutonomyHardeningSoakResult:
    rounds: int
    states_with_churn: int
    internal_reviews_recovered: int
    orphan_running_recovered: int
    protected_gates_preserved: int
    recovery_budget_trips: int
    circuit_trips: int
    goal_closures: int
    violations: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class AutonomyHardeningSoakV1:
    """Adversarial state-machine soak for the post-DEV211 incidents."""

    def run(self, *, rounds: int = 10000, seed: int = 221) -> AutonomyHardeningSoakResult:
        rng = random.Random(seed)
        churn_states = internal_recovered = orphan_recovered = protected_ok = budget_trips = circuit_trips = closures = violations = 0
        for r in range(rounds):
            state = ProjectState(goal=f"hardening-{r}", power_percent=80)
            supervisor = SchedulerProductivitySupervisorV1()
            # Tune test guards to trip quickly while preserving the production defaults.
            supervisor.progress.stall_cycles = 4
            supervisor.progress.control_only_limit = 3
            supervisor.budget.max_recoveries_without_progress = 5
            supervisor.circuit.trip_count = 4

            # Productive branch.
            productive_count = rng.randint(1, 5)
            for i in range(productive_count):
                status = rng.choice([TaskStatus.READY, TaskStatus.COMPLETE, TaskStatus.WAITING])
                t = Task(title=f"productive-{i}", status=status, metadata={"task_role": "productive"})
                if status == TaskStatus.COMPLETE:
                    t.result = "done"; t.metadata["acceptance_evidence"] = True
                state.tasks[t.id] = t; state.root_task_ids.append(t.id)

            # Inject one false internal human review and one orphan worker often.
            internal = Task(title="Continuity recovery: independently verify [cycle 1]",
                            status=TaskStatus.NEEDS_REVIEW,
                            metadata={"task_role": "verification", "continuity_gap_recovery": True, "task_kind": "verification"})
            state.tasks[internal.id] = internal; state.root_task_ids.append(internal.id)
            if rng.random() < 0.55:
                orphan = Task(title="orphan productive", status=TaskStatus.RUNNING, worker_id="ghost", metadata={"task_role": "productive"})
                state.tasks[orphan.id] = orphan; state.root_task_ids.append(orphan.id)
            else:
                orphan = None

            # Protected gate must never be silently recovered. Some rounds omit it
            # so audited completion is also exercised.
            protected = None
            if rng.random() < 0.80:
                protected = Task(title="human protected publish", status=TaskStatus.NEEDS_REVIEW,
                                 metadata={"task_role": "control", "explicit_human_gate": True, "external_action": True})
                state.tasks[protected.id] = protected; state.root_task_ids.append(protected.id)

            # Roughly half the rounds reproduce heavy control churn.
            if rng.random() < 0.55:
                churn_states += 1
                state.metadata["autonomy_recovery_tasks_created"] = rng.randint(10, 900)
                state.metadata["recovery_events"] = [{"kind": "worker_watchdog_recovery", "title": "same"} for _ in range(rng.randint(8, 60))]
                state.metadata["activity_timeline"] = [
                    {"kind": "cognitive_early_abort", "title": "Continuity recovery duplicate"}
                    for _ in range(rng.randint(8, 24))
                ]
                for i in range(rng.randint(3, 9)):
                    x = Task(title="Autonomous recovery duplicate", status=TaskStatus.RETRY,
                             metadata={"task_role": "control", "autonomy_recovery": True, "blocker_signature": "same"})
                    state.tasks[x.id] = x; state.root_task_ids.append(x.id)

            # Occasionally goal audit is already durable PASS.
            if rng.random() < 0.10:
                for t in state.leaf_tasks:
                    if t.metadata.get("task_role") == "productive":
                        t.status = TaskStatus.COMPLETE; t.result = "done"; t.metadata["acceptance_evidence"] = True
                state.metadata["goal_audit_passed"] = True

            active_ids: set[str] = set()
            for _ in range(6):
                before_internal = internal.status
                before_orphan = orphan.status if orphan else None
                report = supervisor.tick(state, active_task_ids=active_ids)
                if before_internal == TaskStatus.NEEDS_REVIEW and internal.status != TaskStatus.NEEDS_REVIEW:
                    internal_recovered += 1
                if orphan and before_orphan == TaskStatus.RUNNING and orphan.status != TaskStatus.RUNNING:
                    orphan_recovered += 1
                if report.recovery_budget_exhausted:
                    budget_trips += 1
                if report.circuit_open:
                    circuit_trips += 1
                if state.completed_at is not None:
                    closures += 1
                    break

            if protected is not None:
                if protected.status == TaskStatus.NEEDS_REVIEW:
                    protected_ok += 1
                else:
                    violations += 1
            active_internal = [t for t in state.leaf_tasks if t.metadata.get("task_role") in {"control", "verification"} and not t.metadata.get("explicit_human_gate") and t.status in {TaskStatus.READY, TaskStatus.RETRY, TaskStatus.RUNNING, TaskStatus.NEEDS_REVIEW}]
            if state.metadata.get("control_plane_recovery_budget_exhausted") and len(active_internal) > 2:
                violations += 1
            if state.completed_at is not None and not state.metadata.get("goal_audit_passed"):
                violations += 1

        return AutonomyHardeningSoakResult(rounds, churn_states, internal_recovered, orphan_recovered, protected_ok, budget_trips, circuit_trips, closures, violations)
