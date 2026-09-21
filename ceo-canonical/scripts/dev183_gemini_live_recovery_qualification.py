from __future__ import annotations
import argparse, asyncio, hashlib, json, subprocess, sys, tempfile
from pathlib import Path
import httpx

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ceo_core.providers.gemini_interactions import GeminiInteractionsTransport
from ceo_core.in_app_updater import InAppUpdater
from ceo_core.security_posture import SecurityPostureGate
from ceo_core.models import ProjectState

BASE_VERSION = '1.4.59-rc1-windows-update-resume'
CANDIDATE_VERSION = '1.4.60-rc1-gemini-live-recovery'
BASE_SHA256 = '765f9cdb9b8bb65d8163bff001f77c7d0bd0777e4e5bf8db6b23a84dd3a805d6'


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def model_order_test() -> dict:
    names = [
        'gemini-2.5-flash-lite', 'gemini-3.1-flash-lite', 'gemini-3.5-flash-lite',
        'gemini-3.6-flash', 'gemini-3.8-flash', 'gemini-3.5-flash',
        'gemini-3-flash-preview', 'gemini-2.5-pro'
    ]
    ordered = sorted(names, key=GeminiInteractionsTransport._model_score)
    expected = ['gemini-3.8-flash', 'gemini-3.6-flash', 'gemini-3.5-flash-lite', 'gemini-3.5-flash', 'gemini-3.1-flash-lite']
    return {'ok': ordered[:5] == expected, 'ordered': ordered, 'expected_prefix': expected}


async def _probe_fallback_success() -> dict:
    t = GeminiInteractionsTransport(api_key='x'*40, model='auto', max_attempts_per_model=1, max_models=8)
    async def models(_client):
        return ['gemini-3.8-flash','gemini-3.6-flash','gemini-3.5-flash-lite','gemini-2.5-flash-lite']
    calls=[]
    async def generate(_client, *, model, contents, max_output_tokens=512):
        calls.append(model)
        if model == 'gemini-3.8-flash':
            req=httpx.Request('POST','https://example.invalid')
            resp=httpx.Response(429,request=req,text='quota')
            raise httpx.HTTPStatusError('quota',request=req,response=resp)
        if model == 'gemini-3.6-flash':
            return {'candidates':[{'content':{'parts':[{'text':'OK'}]}}]}, httpx.Response(200,request=httpx.Request('POST','https://example.invalid'))
        raise AssertionError(model)
    t._candidate_models=models  # type: ignore[method-assign]
    t._generate=generate  # type: ignore[method-assign]
    out=await t.probe_live()
    return {'ok': bool(out.get('ok')) and out.get('model')=='gemini-3.6-flash' and calls==['gemini-3.8-flash','gemini-3.6-flash'], 'calls':calls, 'probe':out}


async def _probe_quota_classification() -> dict:
    t=GeminiInteractionsTransport(api_key='x'*40, model='auto', max_attempts_per_model=1, max_models=8)
    async def models(_client):
        return ['gemini-3.8-flash','gemini-3.6-flash','gemini-3.5-flash-lite']
    async def generate(_client, *, model, contents, max_output_tokens=512):
        req=httpx.Request('POST','https://example.invalid')
        resp=httpx.Response(429,request=req,text='quota')
        raise httpx.HTTPStatusError('quota',request=req,response=resp)
    t._candidate_models=models  # type: ignore[method-assign]
    t._generate=generate  # type: ignore[method-assign]
    out=await t.probe_live()
    return {'ok': out.get('ok') is False and out.get('status')=='QUOTA_EXHAUSTED', 'probe':out}


def startup_preflight() -> dict:
    with tempfile.TemporaryDirectory(prefix='dev183-preflight-') as td:
        cmd=[sys.executable,'-u',str(ROOT/'scripts'/'update_candidate_preflight.py'),'--root',str(ROOT),'--expected-version',CANDIDATE_VERSION,'--sandbox-parent',td,'--timeout','25']
        cp=subprocess.run(cmd,cwd=str(ROOT),capture_output=True,text=True,timeout=45)
        text=((cp.stdout or '')+('\n'+cp.stderr if cp.stderr else '')).strip()
        payload={}
        for line in reversed(text.splitlines()):
            try:
                row=json.loads(line)
                if isinstance(row,dict): payload=row; break
            except Exception: pass
        return {'ok': cp.returncode==0 and payload.get('ok') is True and payload.get('version')==CANDIDATE_VERSION,'returncode':cp.returncode,'detail':text[-3000:]}


def version_order() -> bool:
    cases=[('1.3.47-rc1-governance-fabric',CANDIDATE_VERSION,True),(BASE_VERSION,CANDIDATE_VERSION,True),(CANDIDATE_VERSION,CANDIDATE_VERSION,False),('1.4.61-rc1-future',CANDIDATE_VERSION,False)]
    return all((InAppUpdater._version_key(remote)>InAppUpdater._version_key(cur))==expected for cur,remote,expected in cases)


def package_contract() -> dict:
    row=json.loads((ROOT/'CEO_UPDATE_PACKAGE.json').read_text(encoding='utf-8'))
    bad=[]
    if row.get('app_version')!=CANDIDATE_VERSION: bad.append('app_version')
    req=row.get('required_paths') or []; hashes=row.get('file_hashes') or {}
    for rel in req:
        p=ROOT/rel
        if not p.is_file(): bad.append('missing:'+rel); continue
        if rel=='CEO_UPDATE_PACKAGE.json': continue
        if hashes.get(rel)!=sha256(p): bad.append('hash:'+rel)
    return {'ok':not bad,'required':len(req),'hashes':len(hashes),'bad':bad[:20]}


def security() -> dict:
    st=ProjectState(project_name='DEV183 security')
    r=SecurityPostureGate().assess(st,ROOT)
    return {'ok':bool(r.get('passed')),'files_scanned':int(r.get('files_scanned') or 0),'findings':r.get('findings') or []}


def main() -> int:
    ap=argparse.ArgumentParser(); ap.add_argument('--base-zip',default=''); ap.add_argument('--json',default=''); ns=ap.parse_args()
    base_ok = bool(ns.base_zip and Path(ns.base_zip).is_file() and sha256(Path(ns.base_zip))==BASE_SHA256)
    out={
        'base_version':BASE_VERSION,'candidate_version':CANDIDATE_VERSION,'base_zip_sha256_ok':base_ok,
        'model_order':model_order_test(),
        'fallback_success':asyncio.run(_probe_fallback_success()),
        'quota_classification':asyncio.run(_probe_quota_classification()),
        'startup_preflight':startup_preflight(),
        'version_order':version_order(),
        'package_contract':package_contract(),
        'security':security(),
        'windows_physical_verified':False,
        'gemini_live_verified':False,
        'automatic_spending':False,
        'production_ready':False,
    }
    out['ok']=all([
        out['base_zip_sha256_ok'],out['model_order']['ok'],out['fallback_success']['ok'],out['quota_classification']['ok'],
        out['startup_preflight']['ok'],out['version_order'],out['package_contract']['ok'],out['security']['ok']
    ])
    text=json.dumps(out,ensure_ascii=False,indent=2,sort_keys=True)
    if ns.json: Path(ns.json).write_text(text+'\n',encoding='utf-8')
    print(text)
    return 0 if out['ok'] else 9

if __name__=='__main__':
    raise SystemExit(main())
