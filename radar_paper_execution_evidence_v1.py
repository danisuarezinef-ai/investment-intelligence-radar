"""Read-only PAPER execution/market evidence client. No broker or live-trading authority."""
from __future__ import annotations
import json,os,urllib.error,urllib.request
from typing import Any
from radar_supabase_sync import SYNC_TOKEN,SYNC_URL
REAL_TRADING=False
HTTP_TIMEOUT_SECONDS=35

def _url()->str:
    explicit=os.environ.get('SUPABASE_PAPER_EXECUTION_EVIDENCE_URL','').strip()
    if explicit:return explicit
    base=(SYNC_URL or '').strip()
    if '/radar-sync' in base:return base.rsplit('/radar-sync',1)[0]+'/radar-paper-execution-evidence'
    return 'https://wvmiludqzdepqmjhfwos.supabase.co/functions/v1/radar-paper-execution-evidence'

def enabled()->bool:return bool(_url() and SYNC_TOKEN)

def summary()->dict[str,Any]:
    if not enabled():return {'ok':False,'status':'NOT_CONFIGURED','real_trading':False}
    req=urllib.request.Request(_url(),data=b'{"action":"summary"}',method='POST',headers={'Content-Type':'application/json','X-Radar-Token':SYNC_TOKEN,'User-Agent':'RadarPaperExecutionEvidence/1'})
    try:
        with urllib.request.urlopen(req,timeout=HTTP_TIMEOUT_SECONDS) as r:out=json.loads(r.read().decode('utf-8'))
    except (urllib.error.HTTPError,urllib.error.URLError,TimeoutError,OSError,ValueError) as exc:
        return {'ok':False,'status':'FAIL_CLOSED','error':f'{type(exc).__name__}: {str(exc)[:400]}','real_trading':False}
    if not isinstance(out,dict) or out.get('real_trading') is not False:
        return {'ok':False,'status':'FAIL_CLOSED','error':'invalid execution evidence boundary','real_trading':False}
    return {**out,'status':'EVIDENCE_READY' if out.get('ok') is True else out.get('status','FAIL_CLOSED'),'real_trading':False}
