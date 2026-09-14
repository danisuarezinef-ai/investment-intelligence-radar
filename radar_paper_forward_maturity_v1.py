"""Durable forward-maturity authority client for autonomous PAPER runtime.

This client can only talk to the dedicated Supabase Edge Function. It has no broker,
live-trading, promotion or release authority. Transport or contract ambiguity fails closed.
"""
from __future__ import annotations

import json, os, urllib.error, urllib.request
from typing import Any
from radar_supabase_sync import SYNC_TOKEN, SYNC_URL

REAL_TRADING=False
HTTP_TIMEOUT_SECONDS=35


def _url()->str:
    explicit=os.environ.get('SUPABASE_PAPER_MATURITY_URL','').strip()
    if explicit:return explicit
    base=(SYNC_URL or '').strip()
    if '/radar-sync' in base:return base.rsplit('/radar-sync',1)[0]+'/radar-paper-forward-maturity'
    return 'https://wvmiludqzdepqmjhfwos.supabase.co/functions/v1/radar-paper-forward-maturity'


def enabled()->bool:return bool(_url() and SYNC_TOKEN)


def _post(body:dict[str,Any])->dict[str,Any]:
    if not enabled():return {'ok':False,'status':'NOT_CONFIGURED','real_trading':False}
    req=urllib.request.Request(_url(),data=json.dumps(body,default=str).encode('utf-8'),method='POST',headers={
        'Content-Type':'application/json','X-Radar-Token':SYNC_TOKEN,'User-Agent':'RadarPaperForwardMaturity/1'})
    try:
        with urllib.request.urlopen(req,timeout=HTTP_TIMEOUT_SECONDS) as r:out=json.loads(r.read().decode('utf-8'))
    except (urllib.error.HTTPError,urllib.error.URLError,TimeoutError,OSError,ValueError) as exc:
        return {'ok':False,'status':'FAIL_CLOSED','error':f'{type(exc).__name__}: {str(exc)[:400]}','real_trading':False}
    if not isinstance(out,dict) or out.get('real_trading') is not False:
        return {'ok':False,'status':'FAIL_CLOSED','error':'invalid maturity authority boundary','real_trading':False}
    return {**out,'real_trading':False}


def status()->dict[str,Any]:
    out=_post({'action':'status'})
    a=out.get('authority') if isinstance(out.get('authority'),dict) else {}
    try:hours=float(a.get('valid_forward_hours') or 0)
    except (TypeError,ValueError):hours=0.0
    valid=out.get('ok') is True and hours>=0 and a.get('valid_forward_seconds') is not None
    return {**out,'status':'AUTHORITY_READY' if valid else out.get('status','FAIL_CLOSED'),
            'valid_forward_hours':hours if valid else None,'real_trading':False}


def append_interval(**kw:Any)->dict[str,Any]:
    body={'action':'append','backfilled':False,'downtime':False,'source':'runtime-v23',**kw}
    # Caller cannot enable real trading through this path.
    body.pop('real_trading',None)
    return _post(body)
