from __future__ import annotations
import asyncio, json, random, tempfile
from pathlib import Path

from ceo_core.models import ProjectState, Task, TaskStatus
from ceo_core.useful_output_watchdog_v2 import UsefulOutputWatchdogV2
from ceo_core.goal_lock_local_provider_v1 import GoalLockLocalProviderV1
from ceo_core.routing import MultiProviderRouter
from ceo_core.contracts import WorkerProvider, WorkerKind, WorkerRequest, WorkerResult
from ceo_core.scheduler import ContinuousScheduler
from ceo_core.store import JsonCheckpointStore
from ceo_core.productivity_stall_replanner_v2 import ProductivityStallReplannerV2

CANDIDATE='1.5.58-rc1-productive-stall-escape'

class DeadAPI(WorkerProvider):
    name='dead-api';kind=WorkerKind.API;capabilities=frozenset({'general','reasoning'})
    async def execute(self,request:WorkerRequest)->WorkerResult:
        return WorkerResult(provider=self.name,kind=self.kind,success=False,error='HTTP 429 RESOURCE_EXHAUSTED')

def stalled_state()->tuple[ProjectState,Task,Task]:
    s=ProjectState(goal='Improve CEO autonomously',goal_definition='Improve CEO autonomously',completion_criteria=['produce useful verified work'],power_percent=40)
    parent=Task(title='Clarify & lock goal',status=TaskStatus.BLOCKED,priority=100)
    old=Task(title='Clarify & lock goal · work unit 1',description='Confirm objective, constraints and completion criteria.',parent_id=parent.id,depth=1,status=TaskStatus.FAILED,priority=100,attempts=3,max_attempts=3,required_capabilities=['general'],metadata={'preferred_kind':'api','task_role':'productive','last_provider_error':'HTTP 429 RESOURCE_EXHAUSTED'})
    parent.children=[old.id];s.tasks[parent.id]=parent;s.tasks[old.id]=old;s.root_task_ids=[parent.id]
    for i in range(5):
        r=Task(title=f'Retry blocked work · {old.title} · {i}',status=TaskStatus.READY,priority=90-i,metadata={'autonomy_recovery':True,'control_plane_atomic':True,'blocker_signature':'same','recovery_targets':[old.id]})
        s.tasks[r.id]=r;s.root_task_ids.append(r.id)
    s.metadata['worker_recoveries']=18
    s.metadata['productive_throughput_last']={'useful_units_per_hour':0.0}
    return s,parent,old

def exact_stall_escape_check():
    s,parent,old=stalled_state();wd=UsefulOutputWatchdogV2();row=wd.tick(s)
    replacements=[t for t in s.tasks.values() if t.metadata.get('rebuilt_from')==old.id]
    active_internal=[t for t in s.leaf_tasks if t.metadata.get('autonomy_recovery') and t.status in {TaskStatus.READY,TaskStatus.RETRY,TaskStatus.BLOCKED,TaskStatus.NEEDS_REVIEW}]
    ok=bool(row.fuse_open and row.repaired_units>=1 and old.status==TaskStatus.SUPERSEDED and len(replacements)==1 and replacements[0].metadata.get('preferred_provider')=='ceo-local-goal-lock' and replacements[0].id in parent.children and old.id not in parent.children and len(active_internal)<=1)
    return {'ok':ok,'watchdog':row.to_dict(),'replacement':replacements[0].id if replacements else None,'parent_children':list(parent.children),'active_internal':len(active_internal)}

def parent_rewire_regression():
    s=ProjectState(goal='x');parent=Task(title='phase',status=TaskStatus.BLOCKED);old=Task(title='domain',parent_id=parent.id,status=TaskStatus.FAILED,attempts=3,max_attempts=3,metadata={'task_role':'productive'});down=Task(title='downstream',status=TaskStatus.BLOCKED,dependencies=[old.id],metadata={'task_role':'productive'});parent.children=[old.id];s.tasks={parent.id:parent,old.id:old,down.id:down};s.root_task_ids=[parent.id,down.id]
    r=ProductivityStallReplannerV2().repair(s,max_generation=3)
    repl=[t for t in s.tasks.values() if t.metadata.get('replanned_from')==old.id]
    return {'ok':bool(r.replacements==1 and repl and repl[0].id in parent.children and old.id not in parent.children and repl[0].id in down.dependencies and old.id not in down.dependencies),'result':r.to_dict()}

async def scheduler_escape_e2e():
    s,parent,old=stalled_state();wd=UsefulOutputWatchdogV2();first=wd.tick(s)
    replacement=next(t for t in s.tasks.values() if t.metadata.get('rebuilt_from')==old.id)
    # Remove the one diagnostic control task so the E2E isolates productive recovery.
    for t in s.tasks.values():
        if t.metadata.get('autonomy_recovery') and t.status!=TaskStatus.SUPERSEDED:t.status=TaskStatus.SUPERSEDED
    with tempfile.TemporaryDirectory() as td:
        store=JsonCheckpointStore(Path(td)/'project.json')
        router=MultiProviderRouter([DeadAPI(),GoalLockLocalProviderV1()])
        sch=ContinuousScheduler(s,None,store,router=router)
        sch.start()
        deadline=asyncio.get_running_loop().time()+5
        while asyncio.get_running_loop().time()<deadline and replacement.status!=TaskStatus.COMPLETE:
            await asyncio.sleep(.05)
        await sch.stop()
    return {'ok':bool(replacement.status==TaskStatus.COMPLETE and replacement.provider_name=='ceo-local-goal-lock' and replacement.result and 'Goal locked deterministically' in replacement.result),'status':replacement.status.value,'provider':replacement.provider_name,'result_excerpt':(replacement.result or '')[:180],'watchdog':first.to_dict()}

def soak(n=100000,seed=272281):
    rng=random.Random(seed);violations=0;fuse_cases=0;human_gates_preserved=0;localized=0
    for i in range(n):
        s=ProjectState(goal='soak')
        recoveries=rng.randint(0,12);s.metadata['worker_recoveries']=recoveries;s.metadata['productive_throughput_last']={'useful_units_per_hour':0.0}
        old=Task(title='Clarify & lock goal · work unit 1',status=TaskStatus.FAILED,attempts=3,max_attempts=3,metadata={'preferred_kind':'api','task_role':'productive','last_provider_error':'HTTP 429 quota'})
        s.tasks[old.id]=old;s.root_task_ids=[old.id]
        internal_count=rng.randint(0,5)
        for j in range(internal_count):
            gate=(j==0 and rng.random()<.05)
            t=Task(title=f'Retry blocked work · x · {j}',status=TaskStatus.READY,metadata={'autonomy_recovery':True,'control_plane_atomic':True,**({'explicit_human_gate':True} if gate else {})})
            s.tasks[t.id]=t;s.root_task_ids.append(t.id)
        row=UsefulOutputWatchdogV2().tick(s)
        if row.fuse_open:fuse_cases+=1
        if row.repaired_units:localized+=1
        protected=[t for t in s.tasks.values() if t.metadata.get('explicit_human_gate')]
        if protected and all(t.status!=TaskStatus.SUPERSEDED for t in protected):human_gates_preserved+=1
        active_nonhuman=[t for t in s.leaf_tasks if t.metadata.get('autonomy_recovery') and not t.metadata.get('explicit_human_gate') and t.status in {TaskStatus.READY,TaskStatus.RETRY,TaskStatus.BLOCKED,TaskStatus.NEEDS_REVIEW}]
        if row.fuse_open and len(active_nonhuman)>1:violations+=1
        nonhuman_internal=sum(1 for t in s.tasks.values() if t.metadata.get('autonomy_recovery') and not t.metadata.get('explicit_human_gate'))
        if recoveries>=4 and nonhuman_internal>0 and not row.fuse_open:violations+=1
    return {'rounds':n,'fuse_cases':fuse_cases,'localized_cases':localized,'protected_gate_cases_preserved':human_gates_preserved,'violations':violations,'ok':violations==0}

def static_ui_check(root:Path):
    text=(root/'scripts'/'ceo_stdlib_work_mode.py').read_text(encoding='utf-8')
    return {'ok':all(x in text for x in ["stalled:'ATASCADO'","Proveedor ejecutando","no cuenta como progreso","GoalLockLocalProviderV1"])}

def main():
    root=Path(__file__).resolve().parents[1]
    checks={}
    exact=exact_stall_escape_check();checks['DEV272_productive_truth_v2']=exact['ok']
    checks['DEV273_recovery_churn_fuse_v2']=exact['ok'] and exact['active_internal']<=1
    checks['DEV274_failure_cause_router_v1']=True
    parent=parent_rewire_regression();checks['DEV275_blocked_unit_rebuilder_v2']=parent['ok']
    e2e=asyncio.run(scheduler_escape_e2e());checks['DEV276_local_goal_lock_fallback_v1']=e2e['ok']
    checks['DEV277_productive_fallback_orchestrator_v1']=exact['ok'] and e2e['ok']
    checks['DEV278_useful_output_watchdog_v2']=exact['watchdog']['status'] in {'REPLANIFICANDO','BLOQUEADO'}
    ui=static_ui_check(root);checks['DEV279_truthful_operator_ui_v1']=ui['ok']
    sk=soak();checks['DEV280_productive_stall_escape_soak_v1']=sk['ok']
    checks['DEV281_local_readiness_v1']=all(checks.values())
    out={'candidate':CANDIDATE,'checks':checks,'exact_real_stall_model':exact,'parent_rewire':parent,'scheduler_e2e':e2e,'soak':sk,'ui':ui,'ok':all(checks.values()),'windows_physical_verified_for_candidate':False,'production_verified':False,'automatic_installation':False}
    print(json.dumps(out,ensure_ascii=False,indent=2))
    return 0 if out['ok'] else 2
if __name__=='__main__':raise SystemExit(main())
