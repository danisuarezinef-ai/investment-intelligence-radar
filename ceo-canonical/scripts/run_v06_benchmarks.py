from __future__ import annotations

import asyncio
import json
import os
import tempfile
import time
from pathlib import Path

import psutil

from ceo_core.conversation_controller import ConversationController
from ceo_core.directors import ProjectDirector
from ceo_core.eta_v2 import MonteCarloETAEngine
from ceo_core.models import ProjectState, Task
from ceo_core.resource_governor import ResourceGovernor
from ceo_core.scheduler import ContinuousScheduler
from ceo_core.simulator import SyntheticProvider, synthetic_project
from ceo_core.sqlite_store import SqliteCheckpointStore
from ceo_core.graph import TaskGraph
from ceo_core.store import CheckpointStore


class MemoryStore(CheckpointStore):
    def __init__(self): self.state=None
    def save(self,state): self.state=state
    def load(self): return self.state


class ExactGovernor(ResourceGovernor):
    def __init__(self,n): self.n=n
    def hardware_capacity(self): return self.n
    def target_concurrency(self,power_percent): return self.n
    def adaptive_target(self,power_percent,**kwargs): return self.n
    def snapshot(self): return {"cpu_percent":0,"ram_percent":0,"hardware_worker_capacity":self.n,"logical_cpus":self.n,"ram_total_gb":64,"ram_available_gb":60,"ram_used_gb":4}
    def limits(self,power_percent): return {"total_workers":self.n,"browser_workers":max(1,self.n//3),"api_workers":self.n,"local_workers":self.n,"file_workers":self.n,"ram_soft_percent":90,"cpu_soft_percent":90}


async def stress(workers:int,tasks:int=1000):
    state=synthetic_project(tasks); provider=SyntheticProvider(delay=.002)
    sch=ContinuousScheduler(state,provider,MemoryStore(),governor=ExactGovernor(workers))
    start=time.perf_counter();sch.start()
    while not state.completed_at:
        await asyncio.sleep(.01)
        if time.perf_counter()-start>30: raise TimeoutError((workers,tasks))
    return {"workers":workers,"tasks":tasks,"seconds":round(time.perf_counter()-start,4),"calls":provider.calls,"terminal_failures":sum(t.status.value=='failed' for t in state.leaf_tasks)}


async def fault_test():
    state=synthetic_project(120); provider=SyntheticProvider(delay=.001,fail_every=9,timeout_every=13)
    sch=ContinuousScheduler(state,provider,MemoryStore(),governor=ExactGovernor(40))
    start=time.perf_counter();sch.start()
    while not state.completed_at:
        await asyncio.sleep(.01)
        if time.perf_counter()-start>30:
            return {"completed":False,"failed":sum(t.status.value=='failed' for t in state.leaf_tasks),"calls":provider.calls}
    return {"completed":True,"failed":sum(t.status.value=='failed' for t in state.leaf_tasks),"calls":provider.calls,"seconds":round(time.perf_counter()-start,4)}


class LongTurnProvider(SyntheticProvider):
    async def execute(self, request):
        self.calls += 1
        from ceo_core.contracts import WorkerResult
        if self.calls < 41:
            return WorkerResult(provider=self.name,kind=self.kind,text=f'turn {self.calls} <CEO_RESULT>{{"status":"continue","reason":"more work","next_instruction":"continue independently","followups":[],"requires_user":false}}</CEO_RESULT>',conversation_id='long-session')
        return WorkerResult(provider=self.name,kind=self.kind,text='final <CEO_RESULT>{"status":"complete","reason":"done","followups":[],"requires_user":false}</CEO_RESULT>',conversation_id='long-session')


async def no_user_benchmark():
    state=ProjectState(goal='40-turn autonomous benchmark',goal_definition='40-turn autonomous benchmark');task=Task(title='Long autonomous work',estimated_seconds=.001);state.tasks={task.id:task};state.root_task_ids=[task.id]
    provider=LongTurnProvider(); sch=ContinuousScheduler(state,provider,MemoryStore(),governor=ExactGovernor(1),controller=ConversationController(max_turns=80))
    start=time.perf_counter();sch.start()
    while not state.completed_at:
        await asyncio.sleep(.005)
        if time.perf_counter()-start>30: raise TimeoutError('long turn')
    return {"turns":task.conversation_turns,"human_interventions_avoided":state.human_interventions_avoided,"human_interventions_required":state.human_interventions_required,"seconds":round(time.perf_counter()-start,4)}


async def main():
    process=psutil.Process(os.getpid());sizes=[]
    for n in (100,1000,10000,100000):
        before=process.memory_info().rss; start=time.perf_counter(); state=synthetic_project(n); build=time.perf_counter()-start; after=process.memory_info().rss
        start=time.perf_counter(); audit=TaskGraph().audit(state); dag=time.perf_counter()-start
        start=time.perf_counter(); directors=ProjectDirector().rebuild(state); director_seconds=time.perf_counter()-start
        start=time.perf_counter(); eta=MonteCarloETAEngine(seed=2).estimate(state,simulations=30 if n>=10000 else 80);eta_seconds=time.perf_counter()-start
        db=Path(tempfile.mkdtemp())/'ceo.db'; store=SqliteCheckpointStore(db); start=time.perf_counter(); store.save(state); first=time.perf_counter()-start; start=time.perf_counter(); store.save(state); incremental=time.perf_counter()-start
        sizes.append({"tasks":n,"build_seconds":round(build,4),"rss_delta_mb":round((after-before)/(1024**2),2),"dag_audit_seconds":round(dag,4),"director_seconds":round(director_seconds,4),"director_nodes":len(directors),"eta_engine_seconds":round(eta_seconds,4),"eta_median":eta.median_seconds,"sqlite_first_save_seconds":round(first,4),"sqlite_unchanged_save_seconds":round(incremental,4),"sqlite_mb":round(db.stat().st_size/(1024**2),2),"dag_valid":audit['valid']})
        del state,store,directors
    concurrency=[]
    for w in (10,50,100,500): concurrency.append(await stress(w,1000))
    report={"project_sizes":sizes,"concurrency":concurrency,"fault_injection":await fault_test(),"no_user_40_turn":await no_user_benchmark()}
    Path('reports/MVP_0.6_RC_BENCHMARKS.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))

if __name__=='__main__': asyncio.run(main())
