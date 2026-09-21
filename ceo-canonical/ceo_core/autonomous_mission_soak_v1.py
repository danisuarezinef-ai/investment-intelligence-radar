from __future__ import annotations

import random
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone

from .models import ProjectState, Task, TaskStatus
from .multi_worker_concurrency_v1 import MultiWorkerConcurrencyV1
from .worker_lifecycle_v2 import WorkerLifecycleV2


@dataclass(slots=True)
class MissionSoakResult:
    rounds: int
    tasks_created: int
    tasks_completed: int
    simulated_failures: int
    simulated_restarts: int
    duplicate_allocations: int
    leaked_leases: int
    violations: int

    def to_dict(self) -> dict:
        return asdict(self)


class AutonomousMissionSoakV1:
    def run(self, rounds: int = 3000, seed: int = 211) -> MissionSoakResult:
        rng = random.Random(seed)
        lifecycle = WorkerLifecycleV2()
        allocator = MultiWorkerConcurrencyV1(lifecycle)
        failures = restarts = duplicates = leaked = violations = created = completed = 0
        for r in range(rounds):
            state = ProjectState(goal=f"mission-{r}", power_percent=80)
            tasks: list[Task] = []
            for i in range(rng.randint(3, 8)):
                t = Task(title=f"work-{i}", status=TaskStatus.READY, priority=100-i)
                state.tasks[t.id] = t; state.root_task_ids.append(t.id); tasks.append(t); created += 1
            allocations = allocator.allocate(state, tasks, worker_count=min(4, len(tasks)), prefix=f"r{r}")
            if len({a.task_id for a in allocations}) != len(allocations):
                duplicates += 1; violations += 1
            active = set()
            for a in allocations:
                task = state.tasks[a.task_id]
                if rng.random() < 0.20:
                    failures += 1
                    task.status = TaskStatus.RETRY
                    lifecycle.release(state, task, reason="simulated_failure")
                else:
                    task.status = TaskStatus.COMPLETE; task.result = "done"; completed += 1
                    lifecycle.release(state, task, reason="complete")
            if rng.random() < 0.25:
                restarts += 1
                # Inject one stale RUNNING lease and force expiry/recovery.
                pending = next((t for t in tasks if t.status == TaskStatus.READY), None)
                if pending:
                    lease = lifecycle.claim(state, pending, "restart-worker", ttl_seconds=5, now=datetime.now(timezone.utc)-timedelta(seconds=10))
                    pending.status = TaskStatus.RUNNING
                    lifecycle.reconcile(state, active_task_ids=set(), now=datetime.now(timezone.utc))
                    if pending.status not in {TaskStatus.RETRY, TaskStatus.READY}:
                        violations += 1
            active_rows = [x for x in state.metadata.get(WorkerLifecycleV2.KEY, {}).values() if not x.get("released")]
            leaked += len(active_rows)
            if active_rows:
                violations += 1
        return MissionSoakResult(rounds, created, completed, failures, restarts, duplicates, leaked, violations)
