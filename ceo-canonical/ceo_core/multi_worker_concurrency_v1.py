from __future__ import annotations

from dataclasses import asdict, dataclass

from .models import ProjectState, Task, TaskStatus
from .worker_lifecycle_v2 import WorkerLifecycleV2


@dataclass(slots=True)
class Allocation:
    task_id: str
    worker_id: str
    lease_id: str

    def to_dict(self) -> dict:
        return asdict(self)


class MultiWorkerConcurrencyV1:
    """Collision-free bounded worker allocation using persisted leases."""

    def __init__(self, lifecycle: WorkerLifecycleV2 | None = None) -> None:
        self.lifecycle = lifecycle or WorkerLifecycleV2()

    def allocate(self, state: ProjectState, tasks: list[Task], *, worker_count: int, prefix: str = "worker") -> list[Allocation]:
        count = max(0, int(worker_count))
        allocations: list[Allocation] = []
        seen: set[str] = set()
        candidates = sorted(
            (t for t in tasks if t.status == TaskStatus.READY),
            key=lambda t: (-int(t.priority), t.created_at, t.id),
        )
        for task in candidates:
            if len(allocations) >= count:
                break
            if task.id in seen:
                raise RuntimeError(f"duplicate_candidate:{task.id}")
            seen.add(task.id)
            worker_id = f"{prefix}-{len(allocations)+1}"
            lease = self.lifecycle.claim(state, task, worker_id)
            task.status = TaskStatus.RUNNING
            allocations.append(Allocation(task.id, worker_id, lease.lease_id))
        if len({a.task_id for a in allocations}) != len(allocations):
            raise AssertionError("duplicate task allocation")
        return allocations
