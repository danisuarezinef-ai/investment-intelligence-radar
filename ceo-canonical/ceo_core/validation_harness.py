from __future__ import annotations

import asyncio
import gc
import hashlib
import json
import os
import tempfile
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

import psutil

from .models import ProjectState, TaskStatus
from .resource_governor import ResourceGovernor
from .scheduler import ContinuousScheduler
from .simulator import SyntheticProvider, synthetic_project
from .sqlite_store import SqliteCheckpointStore
from .store import CheckpointStore, JsonCheckpointStore
from .validation import ValidationEvidence, ValidationRegistry


class MemoryStore(CheckpointStore):
    def __init__(self) -> None: self.state=None
    def save(self,state:ProjectState)->None: self.state=state
    def load(self)->ProjectState|None: return self.state


class ExactGovernor(ResourceGovernor):
    def __init__(self,n:int): self.n=max(1,int(n))
    def hardware_capacity(self)->int:return self.n
    def target_concurrency(self,power_percent:int)->int:return self.n
    def adaptive_target(self,power_percent:int,**kwargs)->int:return self.n
    def snapshot(self)->dict[str,float|int]:return {'cpu_percent':0.0,'ram_percent':0.0,'hardware_worker_capacity':self.n,'logical_cpus':self.n,'ram_total_gb':64,'ram_available_gb':60,'ram_used_gb':4}
    def limits(self,power_percent:int)->dict[str,int|float]:return {'total_workers':self.n,'browser_workers':max(1,self.n//4),'api_workers':self.n,'local_workers':self.n,'file_workers':self.n,'ram_soft_percent':90.0,'cpu_soft_percent':90.0}


def _state_digest(state:ProjectState)->str:
    compact=[]
    for tid in sorted(state.tasks):
        t=state.tasks[tid]
        compact.append((tid,t.status.value,t.result,t.conversation_id,t.conversation_turns,tuple(t.dependencies),tuple(t.children)))
    raw=json.dumps(compact,ensure_ascii=False,sort_keys=True,default=str).encode()
    return hashlib.sha256(raw).hexdigest()


def destructive_persistence_validation(task_count:int=2000)->dict[str,Any]:
    with tempfile.TemporaryDirectory() as td:
        root=Path(td)
        state=synthetic_project(task_count)
        ids=list(state.tasks)
        for i,tid in enumerate(ids[:25]):
            state.tasks[tid].status=TaskStatus.RUNNING
            state.tasks[tid].conversation_id=f'conv-{i}'
            state.tasks[tid].conversation_turns=i%5
        json_store=JsonCheckpointStore(root/'state.json')
        json_store.save(state)
        # second save ensures a backup exists
        state.metadata['destructive_marker']='second-save'
        json_store.save(state)
        (root/'state.json').write_text('{"corrupted":',encoding='utf-8')
        recovered=json_store.load()
        json_ok=bool(recovered and len(recovered.tasks)==task_count)
        sqlite=SqliteCheckpointStore(root/'state.db')
        sqlite.save(state)
        full_seq=sqlite.snapshot_full(state)
        loaded=sqlite.load()
        prepared=sqlite.prepare_for_resume(loaded) if loaded else None
        retry_count=sum(t.status==TaskStatus.RETRY for t in prepared.tasks.values()) if prepared else 0
        restored=sqlite.restore_full_snapshot(full_seq)
        return {
            'json_corruption_fallback_ok':json_ok,
            'sqlite_integrity':sqlite.integrity_check(),
            'running_recovered_as_retry':retry_count,
            'expected_running':25,
            'full_snapshot_restore_ok':bool(restored and len(restored.tasks)==task_count),
            'passed':bool(json_ok and sqlite.integrity_check()['ok'] and retry_count==25 and restored and len(restored.tasks)==task_count),
        }


def idempotency_validation(task_count:int=1500,cycles:int=25)->dict[str,Any]:
    with tempfile.TemporaryDirectory() as td:
        store=SqliteCheckpointStore(Path(td)/'idem.db')
        state=synthetic_project(task_count)
        ids=list(state.tasks)
        for tid in ids[:300]:
            t=state.tasks[tid];t.status=TaskStatus.COMPLETE;t.result=f'result-{tid}'
        store.save(state);base=_state_digest(state);base_count=len(state.tasks)
        mismatches=[]
        for i in range(cycles):
            current=store.load(); assert current is not None
            before=len(current.tasks)
            store.save(current)
            current2=store.load(); assert current2 is not None
            if len(current2.tasks)!=base_count or before!=base_count or _state_digest(current2)!=base:
                mismatches.append(i)
        return {'cycles':cycles,'tasks':task_count,'mismatches':mismatches,'passed':not mismatches}


async def _run_stress(workers:int,tasks:int=600,delay:float=.001)->dict[str,Any]:
    state=synthetic_project(tasks);provider=SyntheticProvider(delay=delay)
    sched=ContinuousScheduler(state,provider,MemoryStore(),governor=ExactGovernor(workers))
    start=time.perf_counter();sched.start()
    while not state.completed_at:
        await asyncio.sleep(.005)
        if time.perf_counter()-start>45:
            raise TimeoutError((workers,tasks))
    sec=time.perf_counter()-start
    await sched.stop()
    return {'workers':workers,'tasks':tasks,'seconds':round(sec,4),'throughput':round(tasks/max(sec,.0001),2),'calls':provider.calls}


async def stress_curve_validation()->dict[str,Any]:
    rows=[await _run_stress(w) for w in (5,10,25,50,100,200)]
    best=max(rows,key=lambda r:r['throughput'])
    # We don't require monotonic scaling; physical/live runs decide the true optimum.
    return {'curve':rows,'best_synthetic':best,'passed':all(r['calls']>=r['tasks'] for r in rows)}


async def endurance_validation(tasks:int=1200)->dict[str,Any]:
    state=synthetic_project(tasks)
    state.metadata['enable_v07']=True
    state.metadata['strategic_tick_interval']=10
    state.metadata['max_failure_split_depth']=1
    for i,t in enumerate(state.tasks.values()):
        t.metadata.update({'task_type':'research' if i%2 else 'analysis','uncertainty':.75 if i%7==0 else .25,'impact':.7 if i%11==0 else .4,'expected_novelty':.6})
    provider=SyntheticProvider(delay=.0004,fail_every=13,timeout_every=19)
    sched=ContinuousScheduler(state,provider,MemoryStore(),governor=ExactGovernor(180))
    start=time.perf_counter();sched.start()
    while not state.completed_at:
        await asyncio.sleep(.01)
        if time.perf_counter()-start>60:
            return {'passed':False,'completed':False,'seconds':round(time.perf_counter()-start,3)}
    terminal=sum(t.status==TaskStatus.FAILED for t in state.tasks.values())
    await sched.stop()
    return {
        'passed':terminal==0,
        'completed':True,
        'seconds':round(time.perf_counter()-start,3),
        'tasks_final':len(state.tasks),'calls':provider.calls,
        'terminal_failures':terminal,
        'interventions_required':state.human_interventions_required,
        'interventions_avoided':state.human_interventions_avoided,
    }


def memory_retention_validation(cycles:int=12,tasks_per_cycle:int=5000)->dict[str,Any]:
    proc=psutil.Process(os.getpid());gc.collect();base=proc.memory_info().rss
    samples=[]
    for _ in range(cycles):
        state=synthetic_project(tasks_per_cycle)
        # Touch serialization/graph-like data paths to allocate realistic transient objects.
        _=state.model_dump(mode='json')
        del state;gc.collect();samples.append(proc.memory_info().rss)
    retained=max(0,samples[-1]-base)/(1024**2)
    growth=max(samples)-min(samples) if samples else 0
    # Python allocators retain arenas; a bounded retained footprint is the signal here.
    passed=retained < 160.0
    return {'cycles':cycles,'tasks_per_cycle':tasks_per_cycle,'baseline_mb':round(base/(1024**2),2),'final_mb':round(samples[-1]/(1024**2),2),'retained_delta_mb':round(retained,2),'peak_spread_mb':round(growth/(1024**2),2),'passed':passed}


def resource_governor_observation()->dict[str,Any]:
    g=ResourceGovernor(hard_worker_cap=256)
    snap=g.snapshot();limits={str(p):g.limits(p) for p in (20,50,80,95)}
    return {'environment':'current-container-not-windows','snapshot':snap,'limits':limits,'passed':True,'validated_physical_windows':False}


async def run_local_validation(registry:ValidationRegistry)->dict[str,Any]:
    report:dict[str,Any]={}
    destructive=destructive_persistence_validation();report['destructive_persistence']=destructive
    registry.record('persistence_recovery',ValidationEvidence('v08-persist','destructive','container-linux',destructive['passed'],json.dumps(destructive,default=str)))
    idem=idempotency_validation();report['idempotency']=idem
    registry.record('persistence_recovery',ValidationEvidence('v08-idem','destructive','container-linux',idem['passed'],json.dumps(idem,default=str)))
    stress=await stress_curve_validation();report['stress_curve']=stress
    registry.record('scheduler',ValidationEvidence('v08-stress','synthetic','container-linux',stress['passed'],json.dumps(stress,default=str)))
    endurance=await endurance_validation();report['endurance']=endurance
    registry.record('scheduler',ValidationEvidence('v08-endurance','endurance','container-linux',endurance['passed'],json.dumps(endurance,default=str)))
    registry.record('conversation_controller',ValidationEvidence('v08-endurance-cc','endurance','container-linux',endurance['passed'],f"avoided={endurance.get('interventions_avoided')} required={endurance.get('interventions_required')}"))
    leak=memory_retention_validation();report['memory_retention']=leak
    registry.record('scheduler',ValidationEvidence('v08-leak','endurance','container-linux',leak['passed'],json.dumps(leak,default=str)))
    rg=resource_governor_observation();report['resource_governor']=rg
    registry.record('resource_governor',ValidationEvidence('v08-rg','synthetic','container-linux',True,json.dumps(rg,default=str)))
    return report
