from __future__ import annotations
import asyncio, json, tempfile
from pathlib import Path
from ceo_core.contracts import WorkerKind, WorkerProvider, WorkerRequest, WorkerResult
from ceo_core.models import ProjectState, Task, TaskStatus
from ceo_core.scheduler import ContinuousScheduler
from ceo_core.store import JsonCheckpointStore
from ceo_core.continuity_policy import should_override_cognitive_early_abort

CANDIDATE='1.4.89-rc1-continuity-loop-breaker'

class Provider(WorkerProvider):
    name='dev212-provider'; kind=WorkerKind.MOCK
    capabilities=frozenset({'general','reasoning','verification'})
    def __init__(self): self.calls=0
    def supports(self, task: Task)->bool: return True
    async def execute(self, request: WorkerRequest)->WorkerResult:
        self.calls += 1
        await asyncio.sleep(0.02)
        return WorkerResult(provider=self.name, kind=self.kind, success=True,
                            text='Independent continuity verification completed with evidence.',
                            conversation_id=f'dev212-{self.calls}', metadata={'acceptance_evidence': True})

async def run_case():
    with tempfile.TemporaryDirectory(prefix='dev212-') as td:
        state=ProjectState(goal='continue autonomously', verification_percent=0, power_percent=100,
                           metadata={'strict_completion_audit':False,'require_goal_audit':False,
                                     'completion_confidence_threshold':0.0,'strategic_tick_interval':10000})
        task=Task(title='Continuity recovery: independently verify the new result against the locked goal [cycle 1]',
                  status=TaskStatus.READY, priority=100, estimated_seconds=.02,
                  required_capabilities=['verification'], max_attempts=3,
                  metadata={'continuity_gap_recovery':True,'task_kind':'verification','failure_count':7,
                            'strategy_observations':5,'predicted_success_probability':0.1,'quality_gate_threshold':0.0})
        state.tasks[task.id]=task; state.root_task_ids.append(task.id)
        provider=Provider(); store=JsonCheckpointStore(Path(td)/'state.json')
        scheduler=ContinuousScheduler(state, provider, store); scheduler.start()
        end=asyncio.get_running_loop().time()+3
        while asyncio.get_running_loop().time()<end and task.status not in {TaskStatus.COMPLETE,TaskStatus.FAILED,TaskStatus.NEEDS_REVIEW}:
            await asyncio.sleep(.05)
        await scheduler.stop()
        return {
            'status':task.status.value,
            'provider_calls':provider.calls,
            'override_count':int(task.metadata.get('cognitive_early_abort_override_count',0)),
            'override_recorded':bool(task.metadata.get('cognitive_early_abort_overridden')),
            'human_review':task.status==TaskStatus.NEEDS_REVIEW,
        }

def main()->int:
    direct=ProjectState(goal='direct')
    protected=Task(title='Continuity recovery: publish', metadata={'continuity_gap_recovery':True,'task_kind':'verification','external_action':True})
    normal=Task(title='Normal productive task')
    e2e=asyncio.run(run_case())
    checks={
        'e2e_internal_task_dispatched': e2e['provider_calls']>=1,
        'e2e_not_false_human_review': not e2e['human_review'],
        'e2e_early_abort_overridden': e2e['override_recorded'] and e2e['override_count']>=1,
        'protected_gate_preserved': not should_override_cognitive_early_abort(direct, protected),
        'normal_task_not_overridden': not should_override_cognitive_early_abort(direct, normal),
    }
    ok=all(checks.values())
    print(json.dumps({'ok':ok,'candidate':CANDIDATE,'checks':checks,'e2e':e2e},indent=2,sort_keys=True))
    return 0 if ok else 1
if __name__=='__main__': raise SystemExit(main())
