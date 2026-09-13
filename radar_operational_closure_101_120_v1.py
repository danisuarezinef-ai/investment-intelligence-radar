"""Operational closure tasks 101-120 for autonomous PAPER.
Fail-closed: no calendar maturity, no live authority, REAL_TRADING=False.
"""
from __future__ import annotations
from datetime import datetime,timezone
import hashlib,json,math
REAL_TRADING=False

def _iso(v):
    try:return datetime.fromisoformat(str(v).replace('Z','+00:00')).astimezone(timezone.utc)
    except Exception:return None

def _task(n,status,**e):return {'task':n,'status':status,'evidence':{**e,'real_trading':False},'real_trading':False}

def forward_maturity(intervals):
    valid=0.0; ledger=[]
    for x in intervals or []:
        a,b=_iso(x.get('start')), _iso(x.get('end'))
        seconds=max(0,(b-a).total_seconds()) if a and b and b>=a else 0
        healthy=(x.get('healthy') is True and x.get('exact_restore') is True and x.get('singleton') is True and x.get('persistence_reconciled') is True and x.get('market_data_ok') is True and x.get('backfill') is not True)
        hours=seconds/3600 if healthy else 0.0;valid+=hours
        ledger.append({**x,'eligible':healthy,'credited_hours':hours})
    return valid,ledger

def board(*,deployment=None,integrity=None,task_states=None,intervals=None,e2e=None,restart=None,singleton=None,market=None,pit=None,liquidity=None,execution=None,accounting=None,recovery=None):
    deployment=deployment or {};integrity=integrity or {};task_states=task_states or {};valid,ledger=forward_maturity(intervals or [])
    t=[]
    t.append(_task(101,'PASS' if deployment.get('success') and deployment.get('runtime')=='v19' else 'PENDING',deployment=deployment))
    counts={s:sum(1 for v in task_states.values() if v==s) for s in ('VERIFIED','PARTIAL','PENDING','FAILED')}
    t.append(_task(102,'PASS' if len(task_states)>=100 else 'PARTIAL',counts=counts,total=len(task_states)))
    t.append(_task(103,'PASS' if integrity.get('status')=='PASS' else 'PENDING',integrity=integrity))
    sha_ok=bool(deployment.get('success') and deployment.get('deployed_sha') and deployment.get('deployed_sha')==deployment.get('main_sha'))
    t.append(_task(104,'PASS' if sha_ok else 'PENDING',sha_match=sha_ok,deployed_sha=deployment.get('deployed_sha'),main_sha=deployment.get('main_sha')))
    t.append(_task(105,'PASS' if ledger else 'PENDING_TIME',audited_valid_forward_hours=valid,calendar_time_credit=False))
    t.append(_task(106,'PASS' if ledger else 'PENDING_TIME',ledger=ledger[-100:],downtime_credit=False))
    t.append(_task(107,'PASS' if restart and restart.get('preserves_prior_valid_hours') and restart.get('downtime_credit') is False else 'PENDING_PROOF',restart=restart))
    for n,h in ((108,72),(109,168),(110,720)):t.append(_task(n,'PASS' if valid>=h else 'PENDING_TIME',required_hours=h,audited_valid_forward_hours=valid))
    t.append(_task(111,'PASS' if e2e and e2e.get('full_cycle_proved') else 'PENDING_PROOF',e2e=e2e))
    exact=bool(restart and restart.get('state_hash_equal') and restart.get('session_equal') and restart.get('no_duplicate_orders') and restart.get('backfill') is False)
    t.append(_task(112,'PASS' if exact else 'PENDING_PROOF',restart_exact=exact,restart=restart))
    single=bool(singleton and singleton.get('active_instances')==1 and singleton.get('lease_held') is True)
    t.append(_task(113,'PASS' if single else 'FAIL_CLOSED',singleton=singleton))
    md=market or {};market_ok=bool(md.get('coverage') is not None and md.get('stale_rate') is not None and md.get('gap_rate') is not None and md.get('duplicate_rate') is not None)
    t.append(_task(114,'PASS' if market_ok else 'PENDING_DATA',market_data=md))
    t.append(_task(115,'PASS' if md.get('broken_provider_paths')==0 and md.get('http_404_count')==0 else 'PENDING_DATA',market_data=md))
    t.append(_task(116,'PASS' if pit and pit.get('reconstructable') and pit.get('immutable_snapshot') else 'PENDING_DATA',pit=pit))
    liq=liquidity or {};liq_ok=all(liq.get(k) is not None for k in ('observed_spread','observed_volume','observed_at','source'))
    t.append(_task(117,'PASS' if liq_ok else 'PENDING_DATA',liquidity=liq,imputed=False))
    ex=execution or {};ex_ok=all(ex.get(k) is True for k in ('partial_fills','rejects','cancellations','market_hours','spread','slippage','commissions','liquidity_limits'))
    t.append(_task(118,'PASS' if ex_ok else 'PENDING_IMPLEMENTATION',execution=ex,paper_only=True))
    ac=accounting or {};ac_ok=ac.get('reconciled') is True and ac.get('equation_error')==0
    t.append(_task(119,'PASS' if ac_ok else 'FAIL_CLOSED',accounting=ac))
    rc=recovery or {};rc_ok=all(rc.get(k) is True for k in ('supabase','market_data','timeout','deploy','hung_process'))
    t.append(_task(120,'PASS' if rc_ok else 'PENDING_PROOF',recovery=rc))
    return {'status':'TASKS_101_120_EVALUATED','tasks':t,'audited_valid_forward_hours':valid,'automatic_promotion':False,'automatic_release':False,'setup_1_6_allowed':False,'live_execution_allowed':False,'real_trading':False}
