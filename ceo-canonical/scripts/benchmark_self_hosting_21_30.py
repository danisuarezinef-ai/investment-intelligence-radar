from __future__ import annotations
import json, sys, tempfile, time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))

from ceo_core.contracts import WorkerResult
from ceo_core.models import ProjectState, Task
from ceo_core.self_hosting_tools import (
    ArtifactExchangeLayer, FilesystemOperations, ImmutableRunningVersion,
    ProviderContextRecovery, SelfHostingGitController, SelfHostingWorkspace,
    TerminalController, WorkerSessionManager,
)

start=time.perf_counter(); stats={}

def timed(name, fn):
    t=time.perf_counter(); result=fn(); stats[name]={"elapsed_seconds":round(time.perf_counter()-t,4),**result}


def sessions():
    s=ProjectState(goal='benchmark'); mgr=WorkerSessionManager(); task=Task(id='t',title='x')
    for i in range(2000):
        mgr.record_turn(s,task,provider='openai-responses',request_context={'i':i},result=WorkerResult(provider='openai-responses',text=str(i),conversation_id=f'c-{i}'))
    snap=mgr.snapshot(s,task.id)
    return {'pass':snap['sessions']==1 and snap['turns']==100 and mgr.recover_conversation_id(s,task,'openai-responses')=='c-1999','operations':2000,'retained_turns':snap['turns']}

def artifacts_fs():
    with tempfile.TemporaryDirectory() as td:
        root=Path(td)/'w'; fs=FilesystemOperations(root); s=ProjectState(goal='x'); layer=ArtifactExchangeLayer(root); task=Task(id='t',title='x')
        for i in range(600):
            fs.write_text(f'artifacts/a{i}.txt',f'value-{i}')
            layer.register(s,f'artifacts/a{i}.txt',task_id='t')
        snap=layer.snapshot(s)
        escaped=False
        try: fs.write_text('../escape.txt','bad')
        except Exception: escaped=True
        return {'pass':snap['count']==600 and escaped,'artifacts':snap['count'],'escape_blocked':escaped}

def context():
    s=ProjectState(goal='x',goal_constraints=['stable immutable']); task=Task(id='t',title='x'); s.tasks={'t':task}
    s.metadata['binding_decisions_v2']={f'b{i}':{'statement':f'rule-{i}','authority':1.0} for i in range(100)}
    rec=ProviderContextRecovery()
    for _ in range(1000): rebuilt=rec.rebuild(s,task,provider='openai-responses')
    return {'pass':rebuilt['recovered_context'] and 'rule-99' in str(rebuilt['binding_decisions']),'recoveries':1000,'audit_rows':len(task.metadata[rec.KEY])}

def terminal():
    import sys as _sys
    with tempfile.TemporaryDirectory() as td:
        exe=Path(_sys.executable).name; ctl=TerminalController(td,allowed={exe}); ok=0
        for i in range(12):
            r=ctl.run([_sys.executable,'-c',f"print({i})"]); ok += int(r.ok)
        blocked=False
        try: ctl.run(['sh','-c','echo unsafe'])
        except PermissionError: blocked=True
        return {'pass':ok==12 and blocked,'runs':12,'blocked_unapproved':blocked}

def git_work():
    with tempfile.TemporaryDirectory() as td:
        root=Path(td)/'repo'; root.mkdir(); g=SelfHostingGitController(root); g.initialize(); (root/'a.txt').write_text('base'); g.commit('base')
        commits=0
        for i in range(8):
            g.create_branch(f't{i}',base_ref='main'); (root/'a.txt').write_text(str(i)); commits += int(bool(g.commit(f'c{i}'))); g.git._run('switch','main'); g.git._run('branch','-D',f'ceo/task-t{i}')
        return {'pass':commits==8 and not g.status()['network_actions_performed'],'commits':commits,'network_actions':False}

def workspace():
    with tempfile.TemporaryDirectory() as td:
        base=Path(td); running=base/'stable'; running.mkdir(); (running/'ceo.py').write_text('stable=True\n'); s=ProjectState(goal='self host')
        manager=SelfHostingWorkspace(running,base/'candidates'); row=manager.create(s,label='alpha'); candidate=Path(row['candidate_root']); (candidate/'ceo.py').write_text('stable=False\n')
        v=manager.immutable.verify(s)
        return {'pass':v['unchanged'] and (running/'ceo.py').read_text()=='stable=True\n' and candidate!=running,'candidate_created':candidate.exists(),'running_unchanged':v['unchanged']}

for name,fn in [('sessions',sessions),('artifacts_filesystem',artifacts_fs),('context_recovery',context),('terminal',terminal),('git_local',git_work),('self_hosting_workspace',workspace)]: timed(name,fn)
out={'version':'1.1.0-dev3-self-hosting-tools','scope':'21-30','elapsed_seconds':round(time.perf_counter()-start,4),'stats':stats,'pass':all(v['pass'] for v in stats.values()),'windows_physical':'DEFERRED_BY_USER','live_provider':'NOT_VERIFIED'}
path=ROOT/'reports'/'SELF_HOSTING_21_30_BENCHMARK.json'; path.write_text(json.dumps(out,indent=2),encoding='utf-8'); print(json.dumps(out,indent=2))
