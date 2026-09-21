from __future__ import annotations
import random
from dataclasses import dataclass,asdict
from .models import ProjectState,Task,TaskStatus
from .adaptive_concurrency_governor_v2 import AdaptiveConcurrencyGovernorV2
from .productive_throughput_ledger_v1 import ProductiveThroughputLedgerV1
from .productivity_stall_replanner_v2 import ProductivityStallReplannerV2
from .provider_resilience_v2 import ProviderResilienceV2

@dataclass(slots=True)
class LongHorizonSoakResult:
    rounds:int; productive_tasks:int; productive_completed:int; provider_failures:int; provider_outages:int; restarts:int
    replans:int; control_events:int; max_dry_spell:int; useful_output_intervals:int; protected_gate_violations:int
    duplicate_completions:int; violations:int
    def to_dict(self):return asdict(self)

class LongHorizonMissionSoakV1:
    """Long logical campaign: staged work, outages, restarts and control churn.

    The test deliberately prevents all work from being available at t=0 so a fast
    scheduler cannot turn this into a short burst. Useful-output dry spells are an
    explicit invariant.
    """
    def run(self,*,rounds:int=25000,seed:int=231,task_count:int=240)->LongHorizonSoakResult:
        rng=random.Random(seed); state=ProjectState(goal='long horizon soak',power_percent=90)
        ids=[]; wave=8; release_gap=40
        for i in range(task_count):
            deps=[] if i<wave else [ids[i-wave]]
            release_round=(i//wave)*release_gap
            t=Task(title=f'deliverable-{i+1}',status=TaskStatus.WAITING,
                   dependencies=deps,priority=100-(i%10),estimated_seconds=1+(i%7),
                   metadata={'task_role':'productive','value_score':60+(i%40),'release_round':release_round})
            state.tasks[t.id]=t;state.root_task_ids.append(t.id);ids.append(t.id)
        protected=Task(title='human payment approval',status=TaskStatus.NEEDS_REVIEW,metadata={'task_role':'control','explicit_human_gate':True,'payment':True})
        state.tasks[protected.id]=protected;state.root_task_ids.append(protected.id)
        gov=AdaptiveConcurrencyGovernorV2(); resil=ProviderResilienceV2(); replanner=ProductivityStallReplannerV2(); ledger=ProductiveThroughputLedgerV1()
        current_workers=2; failures=outages=restarts=replans=control_events=dry=maxdry=intervals=0; completed_seen=set();dup=viol=0
        for r in range(rounds):
            for t in state.tasks.values():
                if t.metadata.get('task_role')!='productive' or t.status!=TaskStatus.WAITING: continue
                if int(t.metadata.get('release_round',0))<=r and all(state.tasks[d].status in {TaskStatus.COMPLETE,TaskStatus.SUPERSEDED} for d in t.dependencies): t.status=TaskStatus.READY
            unresolved=[t for t in state.tasks.values() if t.metadata.get('task_role')=='productive' and t.status not in {TaskStatus.COMPLETE,TaskStatus.SUPERSEDED,TaskStatus.PARTIAL_COMPLETE,TaskStatus.COMPLETE_WITH_UNCERTAINTY}]
            if not unresolved: break
            ready=[t for t in unresolved if t.status in {TaskStatus.READY,TaskStatus.RETRY}]
            provider_down = (r>0 and r%31==0)
            if provider_down:
                outages+=1;failures+=1;resil.classify('HTTP 503 temporarily unavailable',1)
            if r>0 and r%43==0:
                restarts+=1
                for t in state.tasks.values():
                    if t.status==TaskStatus.RUNNING:t.status=TaskStatus.RETRY;t.worker_id=None
            if r%7==0: control_events+=1
            fail_rate=min(.5,failures/max(1,r+1)); restart_pressure=min(.5,restarts/max(1,r+1))
            dec=gov.decide(current=current_workers,max_workers=8,throughput=len(completed_seen)/max(1,r+1),failure_rate=fail_rate,restart_pressure=restart_pressure,queue_depth=len(ready))
            current_workers=dec.target;completed_this_round=0
            if not provider_down:
                for t in sorted(ready,key=lambda x:(-x.priority,x.id))[:current_workers]:
                    t.status=TaskStatus.RUNNING
                    if rng.random()<.07:
                        t.attempts+=1;failures+=1
                        if t.attempts<t.max_attempts:t.status=TaskStatus.RETRY
                        else:t.status=TaskStatus.FAILED
                    else:
                        t.status=TaskStatus.COMPLETE;t.result=f'output:{t.id}';t.metadata['acceptance_evidence']=True;t.actual_seconds=float(t.estimated_seconds)
                        if t.id in completed_seen:dup+=1
                        completed_seen.add(t.id);completed_this_round+=1
            if any(t.status in {TaskStatus.FAILED,TaskStatus.BLOCKED} for t in unresolved):
                rp=replanner.repair(state);replans+=rp.requeued+rp.replacements
            if completed_this_round:
                intervals+=1;maxdry=max(maxdry,dry);dry=0
            else:dry+=1
            if protected.status!=TaskStatus.NEEDS_REVIEW:viol+=1
            if r%25==0:ledger.snapshot(state,persist=True)
        maxdry=max(maxdry,dry)
        productive=[t for t in state.tasks.values() if t.metadata.get('task_role')=='productive']
        completed=sum(t.status==TaskStatus.COMPLETE for t in productive)
        unresolved=sum(t.status not in {TaskStatus.COMPLETE,TaskStatus.SUPERSEDED,TaskStatus.PARTIAL_COMPLETE,TaskStatus.COMPLETE_WITH_UNCERTAINTY} for t in productive)
        if unresolved:viol+=1
        if maxdry>60:viol+=1
        if restarts<10 or outages<10:viol+=1
        if dup:viol+=dup
        return LongHorizonSoakResult(r+1,task_count,completed,failures,outages,restarts,replans,control_events,maxdry,intervals,viol,dup,viol)
