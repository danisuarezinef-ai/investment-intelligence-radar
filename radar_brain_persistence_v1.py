"""Content-addressed Supabase persistence for brain evidence/calibration snapshots.

Uses the existing custom x-radar-token transport.  The persistence channel has no
trading, ranking, release or promotion authority.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

from radar_supabase_sync import SYNC_TOKEN, SYNC_URL

REAL_TRADING=False
_LOCK=threading.RLock()
_STATE={'requests':0,'successes':0,'failures':0,'last_error':None,'last_latency_ms':None,
       'last_snapshot_id':None,'last_kind':None,'last_remote_count':None}


def _url():
    explicit=os.environ.get('SUPABASE_BRAIN_EVIDENCE_URL','').strip()
    if explicit:return explicit
    base=(SYNC_URL or '').strip()
    if '/radar-sync' in base:return base.rsplit('/radar-sync',1)[0]+'/radar-brain-evidence'
    return ''


def enabled():return bool(_url() and SYNC_TOKEN)

def _canon(x):return json.dumps(x,sort_keys=True,separators=(',',':'),ensure_ascii=False,default=str)
def _hash(x):return hashlib.sha256(_canon(x).encode('utf-8')).hexdigest()

def _post(action,**body):
    if not enabled():raise RuntimeError('brain evidence persistence not configured')
    raw=json.dumps({'action':action,**body},ensure_ascii=False,default=str).encode('utf-8')
    req=urllib.request.Request(_url(),data=raw,method='POST',headers={'Content-Type':'application/json','X-Radar-Token':SYNC_TOKEN,'User-Agent':'InvestmentIntelligenceRadarBrainEvidence/1'})
    started=time.monotonic()
    with _LOCK:_STATE['requests']+=1
    try:
        with urllib.request.urlopen(req,timeout=10) as response:out=json.loads(response.read().decode('utf-8'))
        if out.get('ok') is not True:raise RuntimeError('brain evidence edge rejected request')
        with _LOCK:
            _STATE['successes']+=1;_STATE['last_error']=None;_STATE['last_latency_ms']=round((time.monotonic()-started)*1000,2)
        return out
    except (urllib.error.URLError,TimeoutError,OSError,ValueError,RuntimeError) as exc:
        with _LOCK:
            _STATE['failures']+=1;_STATE['last_error']=f'{type(exc).__name__}: {str(exc)[:500]}';_STATE['last_latency_ms']=round((time.monotonic()-started)*1000,2)
        raise


def put_snapshot(kind,payload,*,source_max_evaluated_at=None,origin_deployment=None):
    kind=str(kind);payload=dict(payload or {})
    payload['real_trading']=False
    ph=_hash(payload);sid=hashlib.sha256((kind+'|'+str(source_max_evaluated_at or '')+'|'+ph).encode()).hexdigest()
    snapshot={'id':sid,'kind':kind,'observed_at':datetime.now(timezone.utc).isoformat(),
              'source_max_evaluated_at':source_max_evaluated_at,'payload':payload,'payload_hash':ph,
              'origin_deployment':origin_deployment or os.environ.get('RAILWAY_DEPLOYMENT_ID'),'real_trading':False}
    out=_post('put',snapshot=snapshot)
    with _LOCK:_STATE['last_snapshot_id']=sid;_STATE['last_kind']=kind
    return {'id':sid,'payload_hash':ph,'remote':out,'real_trading':False}


def latest(kind,limit=10):
    out=_post('latest',kind=str(kind),limit=max(1,min(50,int(limit))))
    return {**out,'real_trading':False}


def stats():
    out=_post('stats')
    with _LOCK:_STATE['last_remote_count']=out.get('count')
    return {**out,'real_trading':False}


def telemetry():
    with _LOCK:s=dict(_STATE)
    s.update({'configured':enabled(),'durable_backend':'SUPABASE' if enabled() else None,
              'content_addressed':True,'runtime_can_trade':False,'automatic_promotion':False,
              'real_trading':False})
    return s
