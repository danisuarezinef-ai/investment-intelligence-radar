"""Live durable evidence board for autonomous PAPER tasks 21-30.

Reads actual runtime and Supabase evidence. It never backfills observations, invents
maturity, promotes a challenger, submits broker orders, or enables live trading.
"""
from __future__ import annotations

from datetime import datetime, timezone

import radar_decision_memory_v2 as decision_memory
import radar_forward_evidence_v2 as forward
import radar_attribution_v3 as attribution
import radar_simulator_hardening_16_25_v1 as hard
import radar_remote_evidence_21_30_v1 as remote_evidence

REAL_TRADING=False
HORIZON_RULES={'1d':(40,3,8),'1w':(30,7,8),'1m':(25,21,8),'3m':(20,63,8)}


def _now():return datetime.now(timezone.utc).isoformat()
def _dt(v):
    if not v:return None
    try:
        d=datetime.fromisoformat(str(v).replace('Z','+00:00'))
        return d.replace(tzinfo=timezone.utc) if d.tzinfo is None else d.astimezone(timezone.utc)
    except Exception:return None

def _days(a,b):
    x,y=_dt(a),_dt(b)
    return ((y.date()-x.date()).days+1) if x and y and y>=x else 0


def task21_decision_journal(remote):
    local={}
    try:local=decision_memory.memory_health()
    except Exception:pass
    if not remote.get('ok'):
        return {'task':21,'name':'decision_journal','status':'NOT_VERIFIED','durable_authority':False,
                'local_episodes':local.get('episodes'),'error':remote.get('error'),'real_trading':False}
    j=remote.get('journal') or {};n=int(j.get('rows') or 0)
    checks={k:int(j.get(k) or 0)==n and n>0 for k in ('thesis_rows','context_rows','pit_rows','nonretro_rows','paper_rows','decision_rows')}
    return {'task':21,'name':'decision_journal','status':'PASS' if all(checks.values()) else 'PARTIAL',
            'durable_authority':True,'backend':'SUPABASE_DIRECT_DB','rows':n,'checks':checks,
            'first_created':j.get('first_created'),'last_created':j.get('last_created'),
            'append_only_forward_ledger':True,'future_evidence_allowed':False,
            'automatic_promotion':False,'real_trading':False}


def task22_forward_horizons(remote):
    if not remote.get('ok'):
        return {'task':22,'name':'forward_horizons','status':'NOT_VERIFIED','error':remote.get('error'),'real_trading':False}
    out={}
    for row in remote.get('horizons') or []:
        h=str(row.get('horizon'));min_n,min_days,min_assets=HORIZON_RULES.get(h,(10**9,10**9,10**9))
        n=int(row.get('matured') or 0);natural=int(row.get('natural_matured') or 0);assets=int(row.get('matured_assets') or 0)
        days=_days(row.get('first_matured_created'),row.get('last_matured_created'))
        complete=int(row.get('provenance_complete') or 0)>=n
        ok=n>=min_n and natural==n and days>=min_days and assets>=min_assets and complete
        state='PASS' if ok else ('PENDING_TIME' if n and days<min_days else 'PENDING_SAMPLE')
        out[h]={'status':state,'n':n,'natural_n':natural,'calendar_days':days,'assets':assets,
                'provenance_complete':complete,'min_n':min_n,'min_days':min_days,'min_assets':min_assets}
    overall='PASS' if set(out)==set(HORIZON_RULES) and all(v['status']=='PASS' for v in out.values()) else 'PENDING_FORWARD_MATURITY'
    return {'task':22,'name':'forward_horizons','status':overall,'horizons':out,
            'durable_authority':True,'backfill_allowed':False,'real_trading':False}


def task23_forward_attribution(remote):
    if not remote.get('ok'):
        return {'task':23,'name':'forward_attribution','status':'NOT_VERIFIED','error':remote.get('error'),'real_trading':False}
    m=remote.get('maturity') or {};n=int(m.get('matured_1d') or 0)
    complete=n>0 and all(int(m.get(k) or 0)==n for k in ('natural_1d','benchmark_complete','cost_complete','net_complete'))
    # Net/benchmark/cost attribution is durable, but causal component decomposition
    # remains partial until timing/sizing/regime components are prospectively persisted.
    return {'task':23,'name':'forward_attribution','status':'PARTIAL' if complete else 'PENDING_SAMPLE',
            'matured_1d':n,'natural_1d':m.get('natural_1d'),'benchmark_complete':m.get('benchmark_complete'),
            'cost_complete':m.get('cost_complete'),'net_complete':m.get('net_complete'),
            'mean_net_return':m.get('mean_net_return'),'mean_excess_return':m.get('mean_excess_return'),
            'causal_component_decomposition_verified':False,'performance_verified':False,
            'durable_authority':True,'real_trading':False}


def task24_meta_learning():
    return {'task':24,'name':'bounded_meta_learning','status':'GOVERNED_PENDING_SAMPLE',
            'challenger_only':True,'bounded_mutation_required':True,'historical_can_promote':False,
            'automatic_promotion':False,'automatic_champion_replacement':False,'real_trading':False}


def task25_scorecard(simulator_status,milestones,restore,lease,remote):
    paper=(simulator_status or {}).get('paper') or {};aut=(remote.get('autonomy') or {}).get('payload') or {}
    # Do not use wall-clock elapsed_hours as valid forward maturity. Only an explicitly
    # audited valid_forward_hours field may populate this metric.
    valid_hours=(milestones or {}).get('valid_forward_hours')
    metrics={'uptime_pct':None,'cycles':aut.get('completed_cycles',(simulator_status or {}).get('completed_cycles')),
             'decisions':(remote.get('journal') or {}).get('rows'),'trades':paper.get('trades'),'abstentions':None,
             'equity':paper.get('total'),'pnl':paper.get('pnl_pct'),'max_drawdown':paper.get('max_drawdown'),
             'costs':paper.get('costs'),'errors':1 if (simulator_status or {}).get('last_error') else 0,
             'recoveries':1 if (restore or {}).get('status')=='RESTORED_EXACT_PAPER_ENGINE' else 0,
             'persistence_integrity':bool((restore or {}).get('verified')),
             'valid_forward_hours':valid_hours,'return_observations':(remote.get('maturity') or {}).get('matured_1d'),
             'sharpe':None,'sortino':None}
    return {'task':25,'name':'paper_scorecard','status':'OBSERVING','metrics':metrics,
            'wall_clock_maturity_not_counted':True,'lease_status':(lease or {}).get('status'),
            'durable_authority':bool(remote.get('ok')),'real_trading':False}


def task26_lease_continuity(lease):
    l=lease or {};held=l.get('held') is True or l.get('status')=='HELD'
    return {'task':26,'name':'lease_continuity','status':'PASS' if held else 'FAIL_CLOSED','held':held,
            'reacquired':bool(l.get('reacquired')),'error':l.get('error'),'duplicate_instances_allowed':False,'real_trading':False}


def task27_exact_restore(restore):
    r=restore or {};ok=(r.get('status')=='RESTORED_EXACT_PAPER_ENGINE' and r.get('verified') is True and bool(r.get('remote_state_hash')) and r.get('remote_state_hash')==r.get('local_state_hash') and r.get('backfill_used') is False and r.get('reconstructed') is False and r.get('real_trading') is False)
    return {'task':27,'name':'exact_restore','status':'PASS' if ok else 'FAIL_CLOSED','verified':bool(r.get('verified')),
            'hash_equal':bool(r.get('remote_state_hash')) and r.get('remote_state_hash')==r.get('local_state_hash'),
            'schema_version':r.get('local_schema_version'),'backfill_used':r.get('backfill_used'),'reconstructed':r.get('reconstructed'),'real_trading':False}


def task28_reconciliation(local,remote):
    required=('state_hash','session_id','cycle','cash','equity','positions_hash','learning_hash','observed_at')
    missing_local=[k for k in required if (local or {}).get(k) is None];missing_remote=[k for k in required if (remote or {}).get(k) is None]
    if missing_local or missing_remote:
        return {'task':28,'name':'persistence_reconciliation','status':'NOT_VERIFIED','missing_local':missing_local,
                'missing_remote':missing_remote,'silent_overwrite_allowed':False,'new_paper_risk_allowed':False,
                'live_execution_allowed':False,'real_trading':False}
    try:return {'task':28,'name':'persistence_reconciliation',**hard.persistence_reconciliation_gate(local,remote)}
    except Exception as exc:return {'task':28,'name':'persistence_reconciliation','status':'NOT_VERIFIED','error':f'{type(exc).__name__}: {str(exc)[:500]}','real_trading':False}


def task29_disaster_evidence(results=None):
    gate=hard.disaster_test_gate(results or [])
    return {'task':29,'name':'disaster_evidence',**gate,'synthetic_evidence_counts':False}


def task30_composite(tasks):
    blockers=[];acceptable={21:{'PASS'},22:{'PASS'},23:{'PASS'},24:{'GOVERNED_PENDING_SAMPLE','PASS'},25:{'OBSERVING','PASS'},26:{'PASS'},27:{'PASS'},28:{'RECONCILED'},29:{'PASS'}}
    for t in tasks:
        if t.get('task') in acceptable and t.get('status') not in acceptable[t['task']]:blockers.append(f"{t.get('task')}:{t.get('status')}")
    return {'task':30,'name':'production_paper_gate_21_30','status':'PASS' if not blockers else 'PENDING','blockers':blockers,
            'paper_only':True,'live_execution_allowed':False,'automatic_promotion':False,'automatic_release':False,'setup_1_6_allowed':False,'real_trading':False}


def board(*,simulator_status=None,milestones=None,restore=None,lease=None,reconciliation_local=None,reconciliation_remote=None,disaster_results=None):
    remote=remote_evidence.summary()
    tasks=[task21_decision_journal(remote),task22_forward_horizons(remote),task23_forward_attribution(remote),task24_meta_learning(),
           task25_scorecard(simulator_status or {},milestones or {},restore or {},lease or {},remote),task26_lease_continuity(lease or {}),
           task27_exact_restore(restore or {}),task28_reconciliation(reconciliation_local or {},reconciliation_remote or {}),task29_disaster_evidence(disaster_results or [])]
    tasks.append(task30_composite(tasks))
    return {'generated_at':_now(),'remote_evidence_ok':remote.get('ok') is True,'remote_transport':remote.get('transport'),
            'tasks':tasks,'live_execution_allowed':False,'automatic_promotion':False,'automatic_release':False,'setup_1_6_allowed':False,'real_trading':False}
