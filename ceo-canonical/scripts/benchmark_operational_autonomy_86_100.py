from __future__ import annotations
import json, tempfile
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from ceo_core.models import ProjectState
from ceo_core.operational_autonomy import OperationalAutonomyCore, OperationalAction, OperationalRisk


def main():
    with tempfile.TemporaryDirectory(prefix='ceo-op-bench-') as td:
        root=Path(td)
        state=ProjectState(goal='operational benchmark')
        core=OperationalAutonomyCore(root); core.initialize(state)
        safe=0; spend_blocked=0
        for i in range(1000):
            safe += core.policy.decide(OperationalAction(f'write-{i}',OperationalRisk.WRITE))['decision']=='AUTO_APPROVE'
            spend_blocked += core.policy.decide(OperationalAction(f'buy credits {i}',OperationalRisk.SPEND))['decision']=='REQUIRE_APPROVAL'
        handles=[]
        for i in range(250):
            handles.append(core.env.bind_secret(state,name=f'KEY_{i}',value=f'value-{i}',purpose='benchmark'))
        serialized=state.model_dump_json()
        secret_values_persisted=sum(f'value-{i}' in serialized for i in range(250))
        mobile=0; windows=0
        for _ in range(1000):
            mobile += core.router.recommend(task_kind='local_model',estimated_ram_gb=8)['device']=='mobile'
            windows += core.router.recommend(task_kind='windows_ui',estimated_ram_gb=1)['device']=='windows'
        for i in range(200):
            core.record_manual_step(state,action='manual_file_move',description=f'move-{i}')
        tasks=core.create_friction_tasks(state,limit=200)
        duplicates=core.create_friction_tasks(state,limit=200)
        for i in range(250):
            core.files.write_text(f'work/{i}.txt',str(i))
            core.files.copy(f'work/{i}.txt',f'artifacts/{i}.txt')
        smoke=core.supervised_local_smoke(state)
        result={
            'safe_actions_auto_approved':safe,
            'spend_actions_blocked':spend_blocked,
            'secret_handles':len(handles),
            'secret_values_persisted':secret_values_persisted,
            'mobile_routes':mobile,
            'windows_routes':windows,
            'friction_tasks_created':len(tasks),
            'friction_duplicate_tasks_created':len(duplicates),
            'filesystem_roundtrips':250,
            'supervised_smoke_success_rate':smoke['summary']['success_rate'],
        }
        result['pass']=all([
            safe==1000, spend_blocked==1000, secret_values_persisted==0,
            mobile==1000, windows==1000, len(tasks)==200, len(duplicates)==0,
            smoke['summary']['success_rate']==1.0,
        ])
        print(json.dumps(result,indent=2))
        return 0 if result['pass'] else 1
if __name__=='__main__': raise SystemExit(main())
