from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from typing import Any

from .contracts import WorkerKind, WorkerProvider, WorkerRequest, WorkerResult
from .models import ProjectState, Task, TaskStatus
from .scheduler import ContinuousScheduler
from .store import JsonCheckpointStore
from .resource_governor import ResourceGovernor


class _Provider(WorkerProvider):
    name = "dev257-local"
    kind = WorkerKind.MOCK
    capabilities = frozenset({"general"})
    def __init__(self): self.calls = 0
    def supports(self, task) -> bool: return True
    async def execute(self, req: WorkerRequest) -> WorkerResult:
        self.calls += 1
        await asyncio.sleep(0.05)
        return WorkerResult(provider=self.name, kind=self.kind, success=True, text="useful:" + req.work_unit.title, metadata={"acceptance_evidence":True})


async def _run() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="dev257-") as td:
        state = ProjectState(goal="post-update productive continuity", verification_percent=0, power_percent=100,
            metadata={"strict_completion_audit":False,"require_goal_audit":False,"completion_confidence_threshold":0.0,"strategic_tick_interval":10000,"max_parallel_tasks":4})
        tasks=[]; productive_ids=[]
        for i in range(12):
            t=Task(title=f"productive-{i+1}",status=TaskStatus.READY,priority=100-i,estimated_seconds=0.01,required_capabilities=["general"],metadata={"task_role":"productive","quality_gate_threshold":0.0,"value_score":100-i})
            state.tasks[t.id]=t;state.root_task_ids.append(t.id);tasks.append(t);productive_ids.append(t.id)
        store=JsonCheckpointStore(Path(td)/"state.json"); provider=_Provider(); governor=ResourceGovernor(hard_worker_cap=4); s=ContinuousScheduler(state,provider,store,governor=governor); s.start()
        deadline=asyncio.get_running_loop().time()+5
        while asyncio.get_running_loop().time()<deadline and sum(t.status==TaskStatus.COMPLETE for t in tasks)<5: await asyncio.sleep(0.01)
        await s.stop(); first=store.load(); first_done=sum(first.tasks[i].status==TaskStatus.COMPLETE for i in productive_ids if i in first.tasks)
        provider2=_Provider(); s2=ContinuousScheduler(first,provider2,store,governor=ResourceGovernor(hard_worker_cap=4)); s2.start(); deadline=asyncio.get_running_loop().time()+5
        while asyncio.get_running_loop().time()<deadline and any(first.tasks[i].status!=TaskStatus.COMPLETE for i in productive_ids if i in first.tasks): await asyncio.sleep(0.01)
        await s2.stop(); final=store.load(); done=sum(final.tasks[i].status==TaskStatus.COMPLETE for i in productive_ids if i in final.tasks); evidence=len(final.metadata.get("deliverable_evidence_v1",[]) or [])
        return {"ok":done==12 and 5<=first_done<12 and evidence>=12,"total":12,"first_phase_completed":first_done,"completed":done,"evidence":evidence,"provider_calls":provider.calls+provider2.calls,"restart_resume":True,"external_provider_used":False,"spending_attempts":0}


def run_productive_continuity_gate_v2() -> dict[str, Any]: return asyncio.run(_run())
