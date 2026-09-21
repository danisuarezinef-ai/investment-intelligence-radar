from __future__ import annotations
import argparse, hashlib, json, os, shutil, socket, subprocess, sys, tempfile, time, urllib.request, uuid
from pathlib import Path

APP_VERSION='1.4.89-rc1-continuity-loop-breaker'
LAUNCHER_NAME='ABRIR_CEO.cmd'

def local_appdata(): return Path(os.getenv('LOCALAPPDATA') or (Path.home()/'AppData'/'Local'))
def install_root(): return local_appdata()/'Programs'/'CEO de IAs'
def data_root(): return local_appdata()/'CEO de IAs'

def sha256_file(path: Path)->str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
    return h.hexdigest()

def atomic_json(path: Path, payload: dict)->None:
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_name(path.name+f'.tmp-{os.getpid()}-{uuid.uuid4().hex[:8]}')
    try:
        with tmp.open('w',encoding='utf-8',newline='\n') as f:
            json.dump(payload,f,ensure_ascii=False,indent=2,sort_keys=True); f.write('\n'); f.flush(); os.fsync(f.fileno())
        os.replace(tmp,path)
    finally: tmp.unlink(missing_ok=True)

def read_json(path: Path):
    try:
        x=json.loads(path.read_text(encoding='utf-8')); return x if isinstance(x,dict) else None
    except Exception:return None

def ceo_port_in_use(host='127.0.0.1',port=8765):
    try:
        with socket.create_connection((host,port),timeout=.6): return True
    except OSError:return False

def validate_contract(source: Path)->dict:
    row=json.loads((source/'CEO_UPDATE_PACKAGE.json').read_text(encoding='utf-8'))
    if str(row.get('app_version') or '') != APP_VERSION: raise RuntimeError('La version del contrato no coincide con DEV212')
    bad=[]; verified=0
    for rel in row.get('required_paths') or []:
        p=source/rel
        if not p.is_file(): bad.append(f'missing:{rel}'); continue
        if rel=='CEO_UPDATE_PACKAGE.json': continue
        if str((row.get('file_hashes') or {}).get(rel) or '').lower()!=sha256_file(p): bad.append(f'hash:{rel}')
        else: verified+=1
    if bad: raise RuntimeError('Contrato DEV212 invalido: '+', '.join(bad[:8]))
    return {'required':len(row.get('required_paths') or []),'hashes_verified':verified,'ok':True}

def release_only(rel: str)->bool:
    rel=rel.replace('\\','/'); name=Path(rel).name; up=name.upper()
    if rel.startswith('RESULTADOS_CEO/'): return True
    if '/' not in rel and up.startswith('ABRIR_DEV') and up.endswith('.CMD'): return True
    if '/' not in rel and up.startswith('INSTALAR_CEO_') and up.endswith('.CMD'): return True
    if '/' not in rel and up.startswith('ACTUALIZAR_CEO_') and up.endswith('.CMD'): return True
    if '/' not in rel and up.startswith('LEEME_') and up.endswith('.TXT'): return True
    return False

def copy_payload(source: Path,dest: Path)->int:
    c=json.loads((source/'CEO_UPDATE_PACKAGE.json').read_text(encoding='utf-8')); copied=0
    for rel in c.get('required_paths') or []:
        rel=str(rel).replace('\\','/')
        if release_only(rel): continue
        src=source/rel
        if not src.is_file(): raise RuntimeError(f'Payload contractual ausente: {rel}')
        if 'private.key' in rel.lower(): raise RuntimeError(f'Clave privada prohibida: {rel}')
        dst=dest/rel; dst.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(src,dst); copied+=1
    if copied<20 or not (dest/'scripts'/'ceo_stdlib_work_mode.py').is_file(): raise RuntimeError('Payload DEV212 incompleto')
    return copied

def write_runtime_contract(source: Path,dest: Path)->dict:
    src=json.loads((source/'CEO_UPDATE_PACKAGE.json').read_text(encoding='utf-8'))
    files=sorted(p.relative_to(dest).as_posix() for p in dest.rglob('*') if p.is_file() and '__pycache__' not in p.parts and '.pytest_cache' not in p.parts)
    projected=dict(src); projected['contract_scope']='installed-runtime'; projected['source_contract_required_paths']=len(src.get('required_paths') or [])
    projected['required_paths']=files; projected['file_hashes']={rel:sha256_file(dest/rel) for rel in files if rel!='CEO_UPDATE_PACKAGE.json'}
    atomic_json(dest/'CEO_UPDATE_PACKAGE.json',projected)
    return {'scope':'installed-runtime','source_required':len(src.get('required_paths') or []),'runtime_required':len(files),'runtime_hashes':len(projected['file_hashes'])}

def preflight(py: Path, root: Path, timeout=35)->dict:
    probe=root/'scripts'/'update_candidate_preflight.py'
    if not probe.is_file(): raise RuntimeError('Falta update_candidate_preflight.py')
    parent=data_root()/'updates'/'preflight-sandboxes'; parent.mkdir(parents=True,exist_ok=True)
    cp=subprocess.run([str(py),'-u',str(probe),'--root',str(root),'--expected-version',APP_VERSION,'--sandbox-parent',str(parent),'--timeout',str(timeout-5)],cwd=str(root),capture_output=True,text=True,timeout=timeout)
    out=((cp.stdout or '')+('\n'+cp.stderr if cp.stderr else '')).strip()
    if cp.returncode!=0: raise RuntimeError('Preflight DEV212 fallo: '+(out[-1000:] or f'rc={cp.returncode}'))
    return {'ok':True,'output_tail':out[-1200:]}

def health(timeout=35.0)->dict:
    end=time.time()+timeout; last=''
    while time.time()<end:
        try:
            with urllib.request.urlopen('http://127.0.0.1:8765/api/health',timeout=1.2) as r: row=json.loads(r.read(1024*1024).decode('utf-8'))
            if row.get('ok') is True and str(row.get('version') or '')==APP_VERSION:return row
            last=json.dumps(row,ensure_ascii=False)
        except Exception as e:last=str(e)
        time.sleep(.5)
    raise RuntimeError('Health final no confirmo DEV212: '+last[-500:])

def install(source: Path, py: Path)->dict:
    if os.name!='nt': raise RuntimeError('Actualizacion fisica solo en Windows')
    if ceo_port_in_use(): raise RuntimeError('CEO sigue abierto en el puerto 8765. Cierralo antes de actualizar')
    source_contract=validate_contract(source)
    updates=data_root()/'updates'; versions=updates/'versions'; versions.mkdir(parents=True,exist_ok=True)
    current=updates/'current.json'; previous=updates/'previous.json'; old=read_json(current)
    final=versions/APP_VERSION
    if final.exists():
        active=old and Path(str(old.get('root') or '')).resolve()==final.resolve()
        if active: raise RuntimeError('DEV212 ya figura como version activa')
        q=updates/'quarantine'/f'{APP_VERSION}-reinstall-{int(time.time())}'; q.parent.mkdir(parents=True,exist_ok=True); os.replace(final,q)
    staging=versions/f'.staging-{APP_VERSION}-{os.getpid()}'; shutil.rmtree(staging,ignore_errors=True); staging.mkdir(parents=True)
    try:
        copied=copy_payload(source,staging); projection=write_runtime_contract(source,staging); staged=validate_contract(staging); pf=preflight(py,staging)
        atomic_json(staging/'.ceo-update-receipt.json',{'version':APP_VERSION,'root':str(staging),'contract_verified':True,'preflight_ok':True,'installed':False,'health_confirmed':False,'automatic_promotion':False,'requires_human_confirmation':True,'update_kind':'side-by-side'})
        os.replace(staging,final)
    except Exception:
        shutil.rmtree(staging,ignore_errors=True); raise
    if old: atomic_json(previous,old)
    pointer={'version':APP_VERSION,'root':str(final),'launcher':'ABRIR_CEO.cmd','health_path':'/api/health','activated_at':time.strftime('%Y-%m-%dT%H:%M:%S'),'activated_at_epoch':time.time(),'activation_id':uuid.uuid4().hex,'status':'pending_health','human_confirmed':True,'health_confirmed':False,'automatic_promotion':False,'update_kind':'side-by-side'}
    atomic_json(current,pointer)
    root=install_root(); launcher=root/'launcher'/'launch_current_root.py'
    if not launcher.is_file():
        if old: atomic_json(current,old)
        raise RuntimeError('Falta el launcher estable instalado por DEV211')
    logdir=data_root()/'diagnostics'; logdir.mkdir(parents=True,exist_ok=True); log=(logdir/'dev212-update-launch.log').open('w',encoding='utf-8')
    proc=None
    try:
        flags=getattr(subprocess,'CREATE_NEW_PROCESS_GROUP',0)
        proc=subprocess.Popen([str(py),'-u',str(launcher)],cwd=str(root),stdout=log,stderr=subprocess.STDOUT,creationflags=flags)
        row=health()
        pointer.update({'status':'healthy','health_confirmed':True,'health_confirmed_at':time.strftime('%Y-%m-%dT%H:%M:%S')}); atomic_json(current,pointer)
        receipt=read_json(final/'.ceo-update-receipt.json') or {}; receipt.update({'root':str(final),'installed':True,'health_confirmed':True,'installed_at':time.strftime('%Y-%m-%dT%H:%M:%S'),'health':row}); atomic_json(final/'.ceo-update-receipt.json',receipt)
        return {'ok':True,'version':APP_VERSION,'source_contract':source_contract,'runtime_projection':projection,'runtime_contract':staged,'copied':copied,'pointer':pointer,'health':row}
    except Exception as exc:
        if proc is not None and proc.poll() is None:
            try: proc.terminate()
            except Exception: pass
        if old: atomic_json(current,old)
        else: current.unlink(missing_ok=True)
        raise RuntimeError(f'Activacion DEV212 fallo; puntero restaurado: {exc}') from exc
    finally: log.close()

def self_test(source: Path)->dict:
    source_contract=validate_contract(source)
    with tempfile.TemporaryDirectory(prefix='dev212-update-selftest-') as td:
        root=Path(td)/'runtime'; root.mkdir(); copied=copy_payload(source,root); projection=write_runtime_contract(source,root); runtime=validate_contract(root); pf=preflight(Path(sys.executable),root)
        return {'ok':True,'source_contract':source_contract,'runtime_projection':projection,'runtime_contract':runtime,'runtime_boot_preflight':pf,'copied':copied}

def main()->int:
    ap=argparse.ArgumentParser(); ap.add_argument('--source',default=str(Path(__file__).resolve().parents[1])); ap.add_argument('--self-test',action='store_true'); ns=ap.parse_args()
    try:
        row=self_test(Path(ns.source).resolve()) if ns.self_test else install(Path(ns.source).resolve(),install_root()/'runtime'/'python.exe')
        print(json.dumps(row,ensure_ascii=False,indent=2)); return 0
    except Exception as exc:
        print(f'[BLOCKED] {type(exc).__name__}: {exc}'); return 7
if __name__=='__main__': raise SystemExit(main())
