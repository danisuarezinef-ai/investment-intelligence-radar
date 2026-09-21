from __future__ import annotations
import asyncio,json,tempfile
from pathlib import Path
from ceo_core.models import ProjectState,Task,TaskStatus
from ceo_core.contracts import WorkerProvider,WorkerKind,WorkerRequest,WorkerResult
from ceo_core.store import JsonCheckpointStore
from ceo_core.scheduler import ContinuousScheduler
from ceo_core.productive_throughput_ledger_v1 import ProductiveThroughputLedgerV1
from ceo_core.critical_path_eta_v3 import CriticalPathETAV3
from ceo_core.long_horizon_execution_plan_v1 import LongHorizonExecutionPlanV1
from ceo_core.provider_fault_campaign_v1 import ProviderFaultCampaignV1
from ceo_core.restart_continuity_campaign_v3 import RestartContinuityCampaignV3
from ceo_core.adaptive_concurrency_governor_v2 import AdaptiveConcurrencyGovernorV2
from ceo_core.useful_milestone_engine_v1 import UsefulMilestoneEngineV1
from ceo_core.productivity_stall_replanner_v2 import ProductivityStallReplannerV2
from ceo_core.long_horizon_mission_soak_v1 import LongHorizonMissionSoakV1
from ceo_core.long_horizon_autonomy_readiness_v1 import evaluate_long_horizon_readiness_v1

CANDIDATE='1.5.8-rc1-long-horizon-productive-autonomy'

def add(s,t):s.tasks[t.id]=t;s.root_task_ids.append(t.id);return t

def state_fixture():
    s=ProjectState(goal='long horizon',verification_percent=0,power_percent=100,metadata={'strict_completion_audit':False,'require_goal_audit':False,'completion_confidence_threshold':0.0,'strategic_tick_interval':10000,'concurrency_observations':[{'workers':4,'throughput':4.0,'failures':0}]})
    ids=[]
    for i in range(12):
        deps=[] if i<4 else [ids[i-4]]
        t=add(s,Task(title=f'work-{i}',status=TaskStatus.READY if not deps else TaskStatus.WAITING,dependencies=deps,priority=100-i,estimated_seconds=2+i%3,metadata={'task_role':'productive','value_score':80-i}))
        ids.append(t.id)
    return s

def throughput_check():
    s=state_fixture(); list(s.tasks.values())[0].status=TaskStatus.COMPLETE;list(s.tasks.values())[0].result='x';list(s.tasks.values())[0].metadata['acceptance_evidence']=True
    r=ProductiveThroughputLedgerV1().snapshot(s);return r.productive_completed==1 and r.productive_ready>=3

def eta_check():
    s=state_fixture();r=CriticalPathETAV3().estimate(s,workers=4);return r.eta_seconds>=r.critical_path_seconds>0 and r.p90_seconds>r.eta_seconds>r.p10_seconds

def wave_check():
    s=state_fixture();w=LongHorizonExecutionPlanV1().build(s,workers=4);return len(w)>=3 and len(w[0].task_ids)==4 and len({x for q in w for x in q.task_ids})==12

def concurrency_check():
    g=AdaptiveConcurrencyGovernorV2();a=g.decide(current=2,max_workers=8,throughput=1,failure_rate=.01,restart_pressure=.0,queue_depth=10);b=g.decide(current=4,max_workers=8,throughput=1,failure_rate=.4,restart_pressure=.0,queue_depth=10);return a.target==3 and b.target==3

def milestone_check():
    s=state_fixture();m=UsefulMilestoneEngineV1().rank(s);return len(m)>0 and all(m[i].value_per_second>=m[i+1].value_per_second for i in range(len(m)-1))

def replan_check():
    s=ProjectState(goal='stall');t=add(s,Task(title='blocked',status=TaskStatus.FAILED,attempts=0,max_attempts=3,metadata={'task_role':'productive'}));r=ProductivityStallReplannerV2().repair(s);return r.requeued==1 and t.status==TaskStatus.RETRY

class Provider(WorkerProvider):
    name='dev231-provider';kind=WorkerKind.MOCK;capabilities=frozenset({'general'})
    def __init__(self):self.calls=0;self.running=0;self.max_running=0
    def supports(self,task):return True
    async def execute(self,req:WorkerRequest):
        self.calls+=1;self.running+=1;self.max_running=max(self.max_running,self.running)
        try:
            await asyncio.sleep(.02)
            return WorkerResult(provider=self.name,kind=self.kind,success=True,text=f'Verified deliverable {req.work_unit.title}',metadata={'acceptance_evidence':True})
        finally:self.running-=1

async def real_restart_e2e():
    with tempfile.TemporaryDirectory(prefix='dev231-e2e-') as td:
        s=ProjectState(goal='24 long horizon outputs',verification_percent=0,power_percent=100,metadata={'strict_completion_audit':False,'require_goal_audit':False,'completion_confidence_threshold':0.0,'strategic_tick_interval':10000,'concurrency_observations':[{'workers':4,'throughput':4.0,'failures':0}]})
        tasks=[]
        for i in range(24):tasks.append(add(s,Task(title=f'output-{i}',status=TaskStatus.READY,priority=100-(i%10),estimated_seconds=.02,required_capabilities=['general'],metadata={'task_role':'productive','quality_gate_threshold':0.0,'value_score':80})))
        path=Path(td)/'state.json';store=JsonCheckpointStore(path);p=Provider();sch=ContinuousScheduler(s,p,store);sch.start();await asyncio.sleep(.13);await sch.stop()
        first=sum(t.status==TaskStatus.COMPLETE for t in s.tasks.values());loaded=store.load();loaded=store.prepare_for_resume(loaded);p2=Provider();sch2=ContinuousScheduler(loaded,p2,store);sch2.start();deadline=asyncio.get_running_loop().time()+8
        while asyncio.get_running_loop().time()<deadline:
            if all(t.status==TaskStatus.COMPLETE for t in loaded.tasks.values() if t.metadata.get('task_role')=='productive'):break
            await asyncio.sleep(.05)
        await sch2.stop();final=store.load();completed=sum(t.status==TaskStatus.COMPLETE for t in final.tasks.values() if t.metadata.get('task_role')=='productive');evidence=len(final.metadata.get('deliverable_evidence_v1',[]) or []);leases=final.metadata.get('worker_leases_v2',{}) or {};leaked=sum(not x.get('released') for x in leases.values())
        return {'first_phase_completed':first,'completed':completed,'provider_calls':p.calls+p2.calls,'max_parallel':max(p.max_running,p2.max_running),'evidence':evidence,'leaked_leases':leaked,'restart_resume':first<24 and completed==24,'ok':completed==24 and evidence>=24 and leaked==0 and first<24}

def main():
    fault=ProviderFaultCampaignV1().run();restart=RestartContinuityCampaignV3().run(restarts=25);soak=LongHorizonMissionSoakV1().run(rounds=25000,seed=231,task_count=240);e2e=asyncio.run(real_restart_e2e())
    checks={
      'DEV222_productive_throughput_ledger_v1':throughput_check(),
      'DEV223_critical_path_eta_v3':eta_check(),
      'DEV224_long_horizon_execution_plan_v1':wave_check(),
      'DEV225_provider_fault_campaign_v1':fault.violations==0 and fault.spending_attempts==0,
      'DEV226_restart_continuity_campaign_v3':restart.violations==0 and restart.duplicate_ids==0,
      'DEV227_adaptive_concurrency_governor_v2':concurrency_check(),
      'DEV228_useful_milestone_engine_v1':milestone_check(),
      'DEV229_productivity_stall_replanner_v2':replan_check(),
      'DEV230_long_horizon_mission_soak_v1':soak.violations==0 and soak.max_dry_spell<=250,
      'DEV231_real_restart_e2e':e2e['ok'],
    }
    readiness=evaluate_long_horizon_readiness_v1(throughput_ledger=checks['DEV222_productive_throughput_ledger_v1'],critical_path_eta=checks['DEV223_critical_path_eta_v3'],wave_planner=checks['DEV224_long_horizon_execution_plan_v1'],provider_fault_campaign=checks['DEV225_provider_fault_campaign_v1'],restart_continuity=checks['DEV226_restart_continuity_campaign_v3'],adaptive_concurrency=checks['DEV227_adaptive_concurrency_governor_v2'],useful_milestones=checks['DEV228_useful_milestone_engine_v1'],stall_replanner=checks['DEV229_productivity_stall_replanner_v2'],long_soak=checks['DEV230_long_horizon_mission_soak_v1'],dev221_regression=True,clean_package=True)
    ok=all(checks.values()) and readiness.local_candidate_ready
    print(json.dumps({'ok':ok,'candidate':CANDIDATE,'checks':checks,'fault_campaign':fault.to_dict(),'restart_campaign':restart.to_dict(),'soak':soak.to_dict(),'e2e':e2e,'readiness':readiness.to_dict()},indent=2,sort_keys=True));return 0 if ok else 1
if __name__=='__main__':raise SystemExit(main())
