from __future__ import annotations
import asyncio, hashlib, importlib.util, json, os, sys, tempfile, time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
CANDIDATE='1.4.61-rc1-project-handoff-recovery'


def sha256(p:Path)->str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def load_work_mode():
    os.environ['CEO_DATA_DIR']=tempfile.mkdtemp(prefix='dev184-data-')
    p=ROOT/'scripts'/'ceo_stdlib_work_mode.py'
    spec=importlib.util.spec_from_file_location('dev184_work_mode',p)
    mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod

async def bounded_handoff_test(mod):
    from ceo_core.models import ProjectState
    eng=mod.CEOEngine(None)
    eng.execution_enabled=True
    eng.provider_mode='gemini-live-verified-test'
    eng.gemini_model='test-model'
    old=ProjectState(project_name='legacy X',goal='X')
    class HungScheduler:
        def __init__(self):
            self.state=old; self._active={}; self._runner=None
            self._stop=asyncio.Event(); self.store=eng.projects.store(old.id)
            self.store.save(old)
        async def stop(self):
            await asyncio.sleep(60)
    eng.scheduler=HungScheduler(); eng.state=old
    eng.projects.register(old,make_active=True)
    class NewScheduler:
        def __init__(self,state,*args,**kwargs): self.state=state; self.store=args[1] if len(args)>1 else kwargs.get('store'); self._runner=None
        def start(self): pass
    eng.ContinuousScheduler=NewScheduler
    eng._router=lambda: object()
    async def snap():
        return {'project_id':eng.state.id,'goal':eng.state.goal,'project_name':eng.state.project_name,'active':True,'execution_enabled':True,'scheduler_alive':eng.scheduler is not None,'project_handoff':eng.state.metadata.get('project_handoff')}
    eng.snapshot=snap
    t=time.monotonic()
    out=await eng.start_project({'goal':'Nueva misión autónoma real para CEO','name':'DEV184 switch test','power_percent':78})
    elapsed=time.monotonic()-t
    ok=(elapsed<8 and out['goal'].startswith('Nueva misión') and out['project_id']!=old.id and (out.get('project_handoff') or {}).get('forced') is True)
    try: eng.loop.call_soon_threadsafe(eng.loop.stop)
    except Exception: pass
    return {'ok':ok,'elapsed_seconds':round(elapsed,3),'out':out}

def ui_test():
    text=(ROOT/'scripts'/'ceo_stdlib_work_mode.py').read_text(encoding='utf-8')
    return {'ok': all(x in text for x in ['startNewProject()','id="startStatus"','forced_checkpoint','timeout_seconds=4.0'])}

def package_contract():
    row=json.loads((ROOT/'CEO_UPDATE_PACKAGE.json').read_text(encoding='utf-8'))
    bad=[]
    if row.get('app_version')!=CANDIDATE: bad.append('app_version')
    for rel in row.get('required_paths') or []:
        p=ROOT/rel
        if not p.is_file(): bad.append('missing:'+rel); continue
        if rel=='CEO_UPDATE_PACKAGE.json': continue
        if (row.get('file_hashes') or {}).get(rel)!=sha256(p): bad.append('hash:'+rel)
    return {'ok':not bad,'required':len(row.get('required_paths') or []),'hashes':len(row.get('file_hashes') or {}),'bad':bad[:20]}

def main():
    mod=load_work_mode()
    out={'candidate_version':CANDIDATE,'bounded_project_handoff':asyncio.run(bounded_handoff_test(mod)),'ui_status':ui_test(),'package_contract':package_contract(),'windows_physical_verified':False,'automatic_installation':False,'production_ready':False}
    out['ok']=all(v.get('ok') for k,v in out.items() if isinstance(v,dict))
    print(json.dumps(out,ensure_ascii=False,indent=2,sort_keys=True))
    return 0 if out['ok'] else 9
if __name__=='__main__': raise SystemExit(main())
