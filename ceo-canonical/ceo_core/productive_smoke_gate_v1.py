from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from typing import Any

from .contracts import WorkerKind, WorkerProvider, WorkerRequest, WorkerResult
from .models import ProjectState, Task, TaskStatus
from .scheduler import ContinuousScheduler
from .store import JsonCheckpointStore


class _LocalSmokeProvider(WorkerProvider):
    name = "campaign-local-smoke"
    kind = WorkerKind.MOCK
    capabilities = frozenset({"general"})

    def __init__(self):
        self.calls = 0

    def supports(self, task) -> bool:
        return True

    async def execute(self, req: WorkerRequest) -> WorkerResult:
        self.calls += 1
        await asyncio.sleep(0)
        return WorkerResult(provider=self.name, kind=self.kind, success=True, text=f"smoke:{req.work_unit.title}", metadata={"acceptance_evidence": True})


async def run_productive_smoke_gate_v1_async() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="ceo-campaign-smoke-") as td:
        state = ProjectState(goal="post-update productive smoke", verification_percent=0, power_percent=100,
                             metadata={"strict_completion_audit": False, "require_goal_audit": False,
                                       "completion_confidence_threshold": 0.0, "strategic_tick_interval": 10000})
        task = Task(title="prove scheduler can produce one useful local result", status=TaskStatus.READY,
                    priority=100, estimated_seconds=0.01, required_capabilities=["general"],
                    metadata={"task_role": "productive", "quality_gate_threshold": 0.0, "value_score": 100})
        state.tasks[task.id] = task
        state.root_task_ids.append(task.id)
        store = JsonCheckpointStore(Path(td) / "state.json")
        provider = _LocalSmokeProvider()
        scheduler = ContinuousScheduler(state, provider, store)
        scheduler.start()
        deadline = asyncio.get_running_loop().time() + 5
        while asyncio.get_running_loop().time() < deadline and task.status != TaskStatus.COMPLETE:
            await asyncio.sleep(0.02)
        await scheduler.stop()
        loaded = store.load()
        final = loaded.tasks.get(task.id)
        evidence = loaded.metadata.get("deliverable_evidence_v1", []) or []
        ok = bool(final and final.status == TaskStatus.COMPLETE and provider.calls == 1 and len(evidence) >= 1)
        return {"ok": ok, "completed": bool(final and final.status == TaskStatus.COMPLETE), "provider_calls": provider.calls,
                "evidence_records": len(evidence), "external_provider_used": False, "spending_attempts": 0}


def run_productive_smoke_gate_v1() -> dict[str, Any]:
    return asyncio.run(run_productive_smoke_gate_v1_async())
