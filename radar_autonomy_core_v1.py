"""Minimal durable authority for the autonomous PAPER master state.

This deliberately persists/restores only the master counters/timestamps needed for exact
runtime continuity. It does not backfill runs, create forward evidence, submit orders, or
grant promotion/release authority.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from radar_core import con
from radar_supabase_sync import SYNC_TOKEN, SYNC_URL

REAL_TRADING=False
DEFAULT_URL='https://wvmiludqzdepqmjhfwos.supabase.co/functions/v1/radar-autonomy-core'
NODE_ID=os.environ.get('RADAR_NODE_ID','cloud-primary').strip() or 'cloud-primary'
HTTP_TIMEOUT_SECONDS=35
_FIELDS=('status','enabled','generation','last_error','updated_at','last_result','last_cycle_at','next_cycle_at',
        'completed_cycles','last_research_at','next_research_at','queued_experiments','completed_experiments')


def _url():
    explicit=os.environ.get('SUPABASE_AUTONOMY_CORE_URL','').strip()
    if explicit:return explicit
    base=(SYNC_URL or '').strip()
    if '/radar-sync' in base:return base.rsplit('/radar-sync',1)[0]+'/radar-autonomy-core'
    return DEFAULT_URL


def configured():return bool(_url() and SYNC_TOKEN)


def _post(payload,timeout=HTTP_TIMEOUT_SECONDS):
    if not configured():return {'ok':False,'status':'NOT_CONFIGURED','real_trading':False}
    req=urllib.request.Request(_url(),data=json.dumps(payload,ensure_ascii=False,default=str).encode('utf-8'),method='POST',headers={
        'Content-Type':'application/json','X-Radar-Token':SYNC_TOKEN,'User-Agent':'InvestmentIntelligenceRadarAutonomyCore/1'})
    try:
        with urllib.request.urlopen(req,timeout=timeout) as response:out=json.loads(response.read().decode('utf-8'))
        out['real_trading']=False;return out
    except urllib.error.HTTPError as exc:
        body=exc.read().decode('utf-8','replace')
        return {'ok':False,'status':'FAIL_CLOSED','http_status':exc.code,'error':f'HTTP {exc.code}: {body[:500]}','real_trading':False}
    except (urllib.error.URLError,TimeoutError,OSError,ValueError) as exc:
        return {'ok':False,'status':'FAIL_CLOSED','error':f'{type(exc).__name__}: {str(exc)[:500]}','real_trading':False}


def remote_state():return _post({'action':'get','node_id':NODE_ID,'real_trading':False})


def local_state(simulator):
    simulator.init_autonomous_simulator();c=con()
    cols=[r[1] for r in c.execute('pragma table_info(autonomous_simulator_state)').fetchall()]
    row=c.execute('select * from autonomous_simulator_state where id=1').fetchone();c.close()
    raw={k:v for k,v in zip(cols,row)} if row else {}
    return {k:raw.get(k) for k in ('id',)+_FIELDS if k in raw}


def persist_local_state(simulator):
    state=local_state(simulator)
    return _post({'action':'put','node_id':NODE_ID,'state':state,'real_trading':False})


def restore_exact_core(simulator):
    remote=remote_state();item=remote.get('state') if isinstance(remote,dict) else None
    payload=(item or {}).get('payload') if isinstance(item,dict) else None
    if remote.get('ok') is not True or not isinstance(payload,dict):
        return {'status':'BLOCKED_AUTONOMY_CORE','restored':False,'error':remote.get('error') or 'durable autonomy core unavailable','real_trading':False}
    simulator.init_autonomous_simulator();c=con();allowed={r[1] for r in c.execute('pragma table_info(autonomous_simulator_state)').fetchall()}
    keys=[k for k in _FIELDS if k in allowed and k in payload]
    if 'completed_cycles' not in keys or 'generation' not in keys or 'completed_experiments' not in keys:
        c.close();return {'status':'BLOCKED_AUTONOMY_CORE','restored':False,'error':'durable autonomy core incomplete','real_trading':False}
    vals=[]
    for k in keys:
        v=payload.get(k)
        if k=='last_result' and isinstance(v,(dict,list)):v=json.dumps(v,sort_keys=True,default=str)
        vals.append(v)
    c.execute('update autonomous_simulator_state set '+','.join(f'{k}=?' for k in keys)+' where id=1',vals);c.commit();c.close()
    local=local_state(simulator)
    exact=all(local.get(k)==payload.get(k) or (k=='last_result' and str(local.get(k))==json.dumps(payload.get(k),sort_keys=True,default=str)) for k in ('generation','completed_cycles','completed_experiments','last_cycle_at','last_research_at'))
    return {'status':'RESTORED_EXACT_AUTONOMY_CORE' if exact else 'BLOCKED_AUTONOMY_CORE','restored':bool(exact),
            'generation':local.get('generation'),'completed_cycles':local.get('completed_cycles'),
            'completed_experiments':local.get('completed_experiments'),'remote_updated_at':(item or {}).get('updated_at'),
            'backfill_used':False,'reconstructed':False,'real_trading':False}
