from __future__ import annotations
import contextlib, hashlib, http.server, json, os, socketserver, sys, tempfile, threading
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from ceo_core.operational_autonomy import OperationalAutonomyCore, OperationalAction, OperationalRisk, SafeDownloadManager, TrustedScriptRunner
from ceo_core.project_catalog import ProjectCatalog
from ceo_core.runtime import user_data_root
from ceo_core.self_hosting_beta import SelfHostingBetaCore, SupervisedStep

class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self,*args): pass

@contextlib.contextmanager
def local_site(root:Path):
    class Handler(Quiet):
        def __init__(self,*args,**kwargs): super().__init__(*args,directory=str(root),**kwargs)
    server=socketserver.TCPServer(('127.0.0.1',0),Handler)
    t=threading.Thread(target=server.serve_forever,daemon=True);t.start()
    try: yield f'http://127.0.0.1:{server.server_address[1]}'
    finally: server.shutdown();server.server_close();t.join(timeout=2)

def main():
    if os.name!='nt': raise SystemExit('Windows physical validation requires Windows')
    root=user_data_root(); catalog=ProjectCatalog(root/'projects'); pid=catalog.active_project_id()
    if not pid: raise SystemExit('No active CEO project. Open CEO once first.')
    store=catalog.store(pid); state=store.load()
    if state is None: raise SystemExit(f'Could not load active project {pid}')
    workspace=root/'operational_field_workspace'; workspace.mkdir(parents=True,exist_ok=True)
    core=OperationalAutonomyCore(workspace,data_root=root); core.initialize(state)
    beta=SelfHostingBetaCore(); beta.initialize(state)
    sess=beta.usage.start_session(state,label='Operational Autonomy Windows 86-100',field_executed=True,platform='windows',evidence=['operational_autonomy_windows_v1'])
    sid=sess['session_id']; checks={}
    def step(name,ok,details=None,friction=None):
        beta.usage.record_step(state,sid,SupervisedStep(action=name,success=bool(ok),autonomous=True,human_intervention=False,friction=list(friction or []),details=details or {})); checks[name]=bool(ok)
    boot=core.bootstrap.prepare(); tools=boot['executables']; step('workspace_bootstrap',True,boot)
    step('executable_discovery',bool(tools.get('cmd') and tools.get('powershell') and tools.get('git')),tools)
    try:
        core.files.write_text('work/a.txt','alpha'); core.files.copy('work/a.txt','work/b.txt'); core.files.move('work/b.txt','artifacts/b.txt'); core.files.rename('artifacts/b.txt','final.txt')
        step('filesystem_structured_ops',(workspace/'artifacts/final.txt').read_text(encoding='utf-8')=='alpha')
    except Exception as exc: step('filesystem_structured_ops',False,{'error':repr(exc)},['blocker'])
    try:
        script=workspace/'work'/'probe.cmd'; script.parent.mkdir(parents=True,exist_ok=True); script.write_text('@echo off\r\necho CEO_OPERATOR_OK\r\n',encoding='utf-8',newline='')
        digest=hashlib.sha256(script.read_bytes()).hexdigest(); r=core.scripts.run('work/probe.cmd',expected_sha256=digest)
        step('trusted_script_runner',r['ok'] and 'CEO_OPERATOR_OK' in r['stdout'],{'returncode':r.get('returncode'),'sha256':digest})
    except Exception as exc: step('trusted_script_runner',False,{'error':repr(exc)},['blocker'])
    try:
        with tempfile.TemporaryDirectory(prefix='ceo-op-download-') as td:
            site=Path(td); payload=b'CEO operational download proof\n'; (site/'proof.bin').write_bytes(payload)
            with local_site(site) as base:
                digest=hashlib.sha256(payload).hexdigest(); r=core.downloads.download(base+'/proof.bin','downloads/proof.bin',expected_sha256=digest)
                step('safe_download',r['sha256']==digest and r['verified_hash'],r)
    except Exception as exc: step('safe_download',False,{'error':repr(exc)},['blocker'])
    spend=core.policy.decide(OperationalAction('buy prepaid credits',OperationalRisk.SPEND)); step('spend_gate',spend['decision']=='REQUIRE_APPROVAL',spend)
    route=core.router.recommend(task_kind='local_model',estimated_ram_gb=8,mobile_available=True,mobile_ram_gb=24); step('mobile_routing',route['device']=='mobile' and route['user_notice_required'],route)
    completed=beta.complete_session(state,sid); store.save(state); catalog.touch(state)
    result={'project_id':pid,'checks':checks,'all_pass':all(checks.values()),'session':completed['session']['summary'],'metrics':completed['metrics'],'beta':completed['beta'],'production_verified':False}
    out=Path.home()/'Desktop'/'CEO_OPERATIONAL_AUTONOMY_WINDOWS_RESULT.json'; out.write_text(json.dumps(result,indent=2,ensure_ascii=False,default=str),encoding='utf-8')
    print(json.dumps(result,indent=2,ensure_ascii=False,default=str)); print(f'\nSaved: {out}')
    return 0 if result['all_pass'] else 1
if __name__=='__main__': raise SystemExit(main())
