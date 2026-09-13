"""Autonomous PAPER runtime gates 31-40.

These gates convert observed runtime evidence into fail-closed operational verdicts.
They never backfill maturity, synthesize production proof, authorize live trading,
automatically promote a model, release software, or enable Setup 1.6.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable

REAL_TRADING=False


def _utc(value: Any):
    if value in (None,''): return None
    try:d=datetime.fromisoformat(str(value).replace('Z','+00:00'))
    except Exception:return None
    if d.tzinfo is None:return None
    return d.astimezone(timezone.utc)


def task31_persistence_quorum(*, lease:dict|None, core:dict|None, checkpoint:dict|None, reconciliation:dict|None):
    l,c,p,r=lease or {},core or {},checkpoint or {},reconciliation or {}
    checks={
        'lease_held': l.get('held') is True or l.get('status')=='HELD',
        'same_session': bool(l.get('session_id')),
        'core_exact': c.get('status')=='RESTORED_EXACT_AUTONOMY_CORE' or c.get('restored') is True,
        'checkpoint_exact': p.get('status')=='RESTORED_EXACT_PAPER_ENGINE' and p.get('verified') is True,
        'reconciled': r.get('status')=='RECONCILED',
        'no_backfill': c.get('backfill_used') is not True and p.get('backfill_used') is not True,
        'real_trading_frozen': all(x.get('real_trading') is False for x in (l,c,p) if x),
    }
    blockers=[k for k,v in checks.items() if not v]
    return {'task':31,'name':'critical_persistence_quorum','status':'PASS' if not blockers else 'FAIL_CLOSED',
            'checks':checks,'blockers':blockers,'paper_execution_allowed':not blockers,
            'live_execution_allowed':False,'real_trading':False}


def task32_forward_continuity(current:dict|None, previous:dict|None):
    cur,prev=current or {},previous or {}
    cc=int(cur.get('records',0) or 0); pc=int(prev.get('records',0) or 0)
    cm=int(cur.get('matured',0) or 0); pm=int(prev.get('matured',0) or 0)
    checks={
        'records_monotonic':cc>=pc,
        'matured_monotonic':cm>=pm,
        'capture_start_stable':not prev.get('capture_started_at') or cur.get('capture_started_at')==prev.get('capture_started_at'),
        'no_backfill':cur.get('backfill_used') is not True,
        'no_reconstruction':cur.get('reconstructed') is not True,
        'real_trading_frozen':cur.get('real_trading') is False,
    }
    blockers=[k for k,v in checks.items() if not v]
    return {'task':32,'name':'forward_continuity','status':'PASS' if not blockers else 'FAIL_CLOSED',
            'checks':checks,'blockers':blockers,'records':cc,'matured':cm,
            'live_execution_allowed':False,'real_trading':False}


def task33_journal_coverage(evidence:dict|None, *, minimum_current_coverage:float=0.95):
    e=evidence or {};total=int(e.get('decision_rows',0) or 0);context=int(e.get('context_rows',0) or 0)
    prospective_total=int(e.get('prospective_decision_rows',total) or 0)
    prospective_context=int(e.get('prospective_context_rows',context) or 0)
    coverage=(prospective_context/prospective_total) if prospective_total>0 else 0.0
    status='PASS' if prospective_total>0 and coverage>=minimum_current_coverage else ('PARTIAL' if total>0 else 'PENDING_SAMPLE')
    return {'task':33,'name':'journal_coverage','status':status,'historical_rows':total,
            'historical_context_rows':context,'prospective_rows':prospective_total,
            'prospective_context_rows':prospective_context,'prospective_coverage':coverage,
            'retroactive_fill_allowed':False,'live_execution_allowed':False,'real_trading':False}


def task34_point_in_time_provenance(evidence:dict|None):
    e=evidence or {};total=int(e.get('decision_rows',0) or 0)
    pit=int(e.get('pit_rows',0) or 0);nonretro=int(e.get('nonretro_rows',0) or 0);paper=int(e.get('paper_rows',0) or 0)
    checks={'sample':total>0,'pit_complete':total>0 and pit==total,'nonretro_complete':total>0 and nonretro==total,
            'paper_only_complete':total>0 and paper==total}
    blockers=[k for k,v in checks.items() if not v]
    return {'task':34,'name':'point_in_time_provenance','status':'PASS' if not blockers else 'FAIL',
            'checks':checks,'rows':total,'blockers':blockers,'live_execution_allowed':False,'real_trading':False}


def task35_maturity_scheduler(horizons:dict|None):
    h=horizons or {};required=('1d','1w','1m','3m');bad=[];report={}
    for name in required:
        row=h.get(name) or {};n=int(row.get('n',0) or 0);m=int(row.get('matured',0) or 0)
        if m>n:bad.append(name+':matured_gt_total')
        if row.get('future_evidence_used') is True:bad.append(name+':future_evidence')
        if row.get('backfill_used') is True:bad.append(name+':backfill')
        report[name]={'n':n,'matured':m,'status':'ACTIVE' if n>0 else 'WAITING'}
    return {'task':35,'name':'maturity_scheduler','status':'PASS' if not bad else 'FAIL_CLOSED',
            'horizons':report,'blockers':bad,'unmatured_outcomes_used':False,
            'live_execution_allowed':False,'real_trading':False}


def task36_dependency_error_budget(dependencies:Iterable[dict]|None, *, max_critical_failures:int=0):
    rows=[x for x in (dependencies or []) if isinstance(x,dict)]
    critical=[x for x in rows if x.get('critical') is True and str(x.get('status')) not in {'OK','PASS','HEALTHY','RECONCILED'}]
    degraded=[x for x in rows if str(x.get('status')) in {'DEGRADED','TIMEOUT','STALE','ERROR'}]
    status='PASS' if len(critical)<=max_critical_failures else 'FAIL_CLOSED'
    return {'task':36,'name':'dependency_error_budget','status':status,'critical_failures':len(critical),
            'degraded_dependencies':[x.get('name') for x in degraded],'fail_closed_required':bool(critical),
            'live_execution_allowed':False,'real_trading':False}


def task37_recovery_ledger(events:Iterable[dict]|None):
    rows=[x for x in (events or []) if isinstance(x,dict)]
    invalid=[];recoveries=0
    for i,r in enumerate(rows):
        if r.get('recovery_mode')=='EXACT_PAPER':
            recoveries+=1
            if r.get('state_hash_equal') is not True or r.get('session_continuity') is not True:invalid.append(i)
        if r.get('backfill_used') is True or r.get('real_trading') is not False:invalid.append(i)
    return {'task':37,'name':'recovery_ledger','status':'PASS' if rows and not invalid else ('PENDING_SAMPLE' if not rows else 'FAIL'),
            'events':len(rows),'exact_recoveries':recoveries,'invalid_indexes':sorted(set(invalid)),
            'live_execution_allowed':False,'real_trading':False}


def task38_replay_readiness(replay:dict|None):
    r=replay or {};checks={'decision_snapshot':bool(r.get('decision_snapshot_hash')),
                           'market_snapshot':bool(r.get('market_snapshot_hash')),
                           'config_snapshot':bool(r.get('config_hash')),
                           'model_version':bool(r.get('model_version')),
                           'same_output':r.get('deterministic_output_equal') is True,
                           'no_future_data':r.get('future_data_used') is False,
                           'real_trading_frozen':r.get('real_trading') is False}
    blockers=[k for k,v in checks.items() if not v]
    return {'task':38,'name':'deterministic_replay','status':'PASS' if not blockers else 'PENDING',
            'checks':checks,'blockers':blockers,'live_execution_allowed':False,'real_trading':False}


def task39_learning_integrity(learning:dict|None):
    l=learning or {};checks={'challenger_only':l.get('challenger_only') is True,
        'bounded_mutation':l.get('bounded_mutation') is True,'historical_cannot_promote':l.get('historical_can_promote') is False,
        'automatic_promotion_off':l.get('automatic_promotion') is False,'champion_immutable':l.get('mutates_active_champion') is not True,
        'real_trading_frozen':l.get('real_trading') is False}
    blockers=[k for k,v in checks.items() if not v]
    return {'task':39,'name':'learning_integrity','status':'PASS' if not blockers else 'FAIL_CLOSED',
            'checks':checks,'blockers':blockers,'live_execution_allowed':False,'real_trading':False}


def task40_composite(tasks:Iterable[dict]|None, *, task28_status:str|None=None, task29_status:str|None=None):
    rows=[x for x in (tasks or []) if isinstance(x,dict)];allowed={31:{'PASS'},32:{'PASS'},33:{'PASS','PARTIAL'},34:{'PASS'},35:{'PASS'},36:{'PASS'},37:{'PASS','PENDING_SAMPLE'},38:{'PASS','PENDING'},39:{'PASS'}}
    blockers=[]
    if task28_status!='RECONCILED':blockers.append('28:'+str(task28_status))
    if task29_status!='PASS':blockers.append('29:'+str(task29_status))
    for r in rows:
        n=r.get('task');s=r.get('status')
        if n in allowed and s not in allowed[n]:blockers.append(f'{n}:{s}')
    return {'task':40,'name':'autonomous_paper_gate_31_40','status':'PASS' if not blockers else 'PENDING',
            'blockers':blockers,'paper_only':True,'live_execution_allowed':False,'automatic_promotion':False,
            'automatic_release':False,'setup_1_6_allowed':False,'real_trading':False}


def board(**kwargs):
    tasks=[
        task31_persistence_quorum(lease=kwargs.get('lease'),core=kwargs.get('core'),checkpoint=kwargs.get('checkpoint'),reconciliation=kwargs.get('reconciliation')),
        task32_forward_continuity(kwargs.get('forward_current'),kwargs.get('forward_previous')),
        task33_journal_coverage(kwargs.get('journal')),
        task34_point_in_time_provenance(kwargs.get('journal')),
        task35_maturity_scheduler(kwargs.get('horizons')),
        task36_dependency_error_budget(kwargs.get('dependencies')),
        task37_recovery_ledger(kwargs.get('recoveries')),
        task38_replay_readiness(kwargs.get('replay')),
        task39_learning_integrity(kwargs.get('learning')),
    ]
    tasks.append(task40_composite(tasks,task28_status=kwargs.get('task28_status'),task29_status=kwargs.get('task29_status')))
    return {'generated_at':datetime.now(timezone.utc).isoformat(),'tasks':tasks,'live_execution_allowed':False,
            'automatic_promotion':False,'automatic_release':False,'setup_1_6_allowed':False,'real_trading':False}
