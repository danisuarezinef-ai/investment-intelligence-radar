from __future__ import annotations

import asyncio
import random
import time
from dataclasses import dataclass

from .contracts import WorkerKind, WorkerProvider, WorkerRequest, WorkerResult
from .models import ProjectState, Task


def synthetic_project(task_count: int, *, chain_every: int = 0) -> ProjectState:
    state = ProjectState(goal=f"Synthetic {task_count}", goal_definition="Load-test CEO core")
    previous: str | None = None
    for i in range(task_count):
        deps = [previous] if chain_every and previous and i % chain_every == 0 else []
        task = Task(title=f"Synthetic task {i}", priority=50 + (i % 50), estimated_seconds=0.001, dependencies=deps)
        state.tasks[task.id] = task; state.root_task_ids.append(task.id); previous = task.id
    return state


class SyntheticProvider(WorkerProvider):
    name = "synthetic"
    kind = WorkerKind.MOCK
    capabilities = frozenset({"general"})

    def __init__(self, delay: float = 0.0, fail_every: int = 0, timeout_every: int = 0) -> None:
        self.delay=delay; self.fail_every=fail_every; self.timeout_every=timeout_every; self.calls=0

    async def execute(self, request: WorkerRequest) -> WorkerResult:
        self.calls += 1
        call_no = self.calls
        if self.delay: await asyncio.sleep(self.delay)
        if self.timeout_every and call_no % self.timeout_every == 0:
            raise TimeoutError("fault injection timeout")
        if self.fail_every and call_no % self.fail_every == 0:
            return WorkerResult(provider=self.name, kind=self.kind, success=False, error="fault injection failure")
        return WorkerResult(provider=self.name, kind=self.kind, text=f"Synthetic completion {request.work_unit.id}")


@dataclass(slots=True)
class SimulationResult:
    tasks: int
    build_seconds: float
    state_bytes: int


def profile_project_size(task_count: int) -> SimulationResult:
    start=time.perf_counter(); state=synthetic_project(task_count); build=time.perf_counter()-start
    state_bytes=len(state.model_dump_json())
    return SimulationResult(task_count, round(build,4), state_bytes)
