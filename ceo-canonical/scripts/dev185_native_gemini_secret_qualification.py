from __future__ import annotations
import asyncio, importlib.util, json, os, tempfile, hashlib
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
CANDIDATE='1.4.62-rc1-native-gemini-secret'


def sha256(p:Path)->str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def load_work_mode():
    os.environ['CEO_DATA_DIR']=tempfile.mkdtemp(prefix='dev185-data-')
    os.environ['CEO_KEY_IN_BROWSER']='1'
    p=ROOT/'scripts'/'ceo_stdlib_work_mode.py'
    spec=importlib.util.spec_from_file_location('dev185_work_mode',p)
    mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod


def dpapi_storage_flow_test(mod):
    td=Path(tempfile.mkdtemp(prefix='dev185-localappdata-'))
    old_local=os.environ.get('LOCALAPPDATA')
    old_platform=mod.sys.platform
    old_protect=mod._windows_dpapi_protect_text
    old_unprotect=mod._windows_dpapi_unprotect_text
    key='AIza'+'A'*35
    try:
        os.environ['LOCALAPPDATA']=str(td)
        mod.sys.platform='win32'
        mod._windows_dpapi_protect_text=lambda value: b'cipher:' + value.encode('utf-8')
        mod._windows_dpapi_unprotect_text=lambda blob: blob[len(b'cipher:'):].decode('utf-8') if blob.startswith(b'cipher:') else None
        saved=mod._save_windows_dpapi_gemini_key(key)
        path=mod._gemini_secret_path()
        loaded=mod._load_windows_dpapi_gemini_key()
        plaintext_on_disk=(key.encode('utf-8') in path.read_bytes()) if path.exists() else True
        forgotten=mod._forget_windows_dpapi_gemini_key()
        gone=not path.exists()
        return {'ok': bool(saved and loaded==key and not plaintext_on_disk and forgotten and gone),
                'saved':bool(saved),'loaded_matches':loaded==key,'plaintext_on_disk':plaintext_on_disk,'forgotten':bool(forgotten),'gone':gone}
    finally:
        mod.sys.platform=old_platform
        mod._windows_dpapi_protect_text=old_protect
        mod._windows_dpapi_unprotect_text=old_unprotect
        if old_local is None: os.environ.pop('LOCALAPPDATA',None)
        else: os.environ['LOCALAPPDATA']=old_local


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
            self._stop=asyncio.Event(); self.store=eng.projects.store(old.id); self.store.save(old)
        async def stop(self): await asyncio.sleep(60)
    eng.scheduler=HungScheduler(); eng.state=old; eng.projects.register(old,make_active=True)
    class NewScheduler:
        def __init__(self,state,*args,**kwargs): self.state=state; self.store=args[1] if len(args)>1 else kwargs.get('store'); self._runner=None
        def start(self): pass
    eng.ContinuousScheduler=NewScheduler; eng._router=lambda: object()
    async def snap():
        return {'project_id':eng.state.id,'goal':eng.state.goal,'project_name':eng.state.project_name,'active':True,'execution_enabled':True,'scheduler_alive':eng.scheduler is not None,'project_handoff':eng.state.metadata.get('project_handoff')}
    eng.snapshot=snap
    out=await eng.start_project({'goal':'Nueva mision autonoma real para CEO','name':'DEV185 regression','power_percent':78})
    ok=(out['goal'].startswith('Nueva mision') and out['project_id']!=old.id and (out.get('project_handoff') or {}).get('forced') is True)
    try: eng.loop.call_soon_threadsafe(eng.loop.stop)
    except Exception: pass
    return {'ok':ok,'forced':bool((out.get('project_handoff') or {}).get('forced'))}


def source_contract_test():
    text=(ROOT/'scripts'/'ceo_stdlib_work_mode.py').read_text(encoding='utf-8')
    required=[
        '_load_windows_dpapi_gemini_key()',
        '_save_windows_dpapi_gemini_key(key)',
        'CEO-de-IAs|Gemini|DPAPI|v1',
        '/api/session-key/forget',
        'windows-dpapi',
    ]
    order_ok=text.find('_load_windows_dpapi_gemini_key()') < text.find('_read_windows_clipboard_gemini_key()')
    return {'ok':all(x in text for x in required) and order_ok,'order_dpapi_before_clipboard':order_ok}


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
    out={
        'candidate_version':CANDIDATE,
        'dpapi_storage_flow':dpapi_storage_flow_test(mod),
        'source_contract':source_contract_test(),
        'project_handoff_regression':asyncio.run(bounded_handoff_test(mod)),
        'package_contract':package_contract(),
        'windows_dpapi_physical_verified':False,
        'gemini_live_physical_verified':False,
        'automatic_installation':False,
        'production_ready':False,
    }
    out['ok']=all(v.get('ok') for v in out.values() if isinstance(v,dict))
    print(json.dumps(out,ensure_ascii=False,indent=2,sort_keys=True))
    return 0 if out['ok'] else 9

if __name__=='__main__': raise SystemExit(main())
