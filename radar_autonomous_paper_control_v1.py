"""Autonomous PAPER learning control plane.

This module starts and supervises the existing autonomous PAPER simulator, records
content-addressed remote checkpoints, exposes an independent Simulator Autonomous
Gate, and measures real-time 72h/7d/30d milestones. It never grants live-trading,
release, champion-promotion, or forward-evidence authority.
"""
from __future__ import annotations

import os
import threading
import time
from datetime import datetime, timezone
from typing import Any

import radar_autonomous_simulator_v1 as simulator
import radar_autonomy_e2e_v1 as e2e
import radar_brain_persistence_v1 as persistence
from radar_forward_evidence_v2 import canonical_forward_rows

REAL_TRADING=False
SESSION_KIND='autonomous_paper_session_v1'
CHECKPOINT_KIND='autonomous_paper_checkpoint_v1'
JOURNAL_KIND='autonomous_paper_decision_journal_v1'
REPORT_DAILY_KIND='autonomous_paper_daily_report_v1'
REPORT_WEEKLY_KIND='autonomous_paper_weekly_report_v1'
_LOCK=threading.RLock()
_STARTED=False
_THREADS:dict[str,threading.Thread]={}
_STATE={
    'started_epoch':None,'last_supervisor_epoch':None,'last_checkpoint_epoch':None,
    'last_checkpoint_id':None,'last_journal_run_id':None,'last_error':None,
    'remote_restore':'NOT_ATTEMPTED','session':None,'alerts':[],
}


def _utcnow():return datetime.now(timezone.utc)
def _iso():return _utcnow().isoformat()

def _parse(v):
    if not v:return None
    try:
        d=datetime.fromisoformat(str(v).replace('Z','+00:00'));return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:return None


def _age_seconds(v):
    d=_parse(v)
    return max(0.0,(_utcnow()-d).total_seconds()) if d else None


def _remote_latest(kind:str):
    if not persistence.enabled():return None
    try:
        out=persistence.latest(kind,limit=1);items=list(out.get('items') or [])
        return items[0] if items else None
    except Exception as exc:
        with _LOCK:_STATE['last_error']=f'{type(exc).__name__}: {str(exc)[:500]}'
        return None


def restore_remote_state():
    """Restore only simulator control metadata; PAPER money/state has its own authority."""
    item=_remote_latest(CHECKPOINT_KIND)
    if not item:
        with _LOCK:_STATE['remote_restore']='NO_REMOTE_CHECKPOINT'
        return {'status':'NO_REMOTE_CHECKPOINT','real_trading':False}
    p=dict(item.get('payload') or {})
    safe={k:p.get(k) for k in ('generation','completed_cycles','completed_experiments','last_cycle_at','last_research_at') if p.get(k) is not None}
    # Never restore account balances, positions, orders, forward evidence, or promotion state here.
    try:
        if safe:
            simulator._set(**safe)
        with _LOCK:_STATE['remote_restore']='RESTORED_CONTROL_METADATA'
        return {'status':'RESTORED_CONTROL_METADATA','fields':sorted(safe),'source_snapshot_id':item.get('id'),'real_trading':False}
    except Exception as exc:
        with _LOCK:
            _STATE['remote_restore']='RESTORE_FAILED';_STATE['last_error']=f'{type(exc).__name__}: {str(exc)[:500]}'
        return {'status':'RESTORE_FAILED','error':str(exc)[:500],'real_trading':False}


def _load_or_create_session():
    with _LOCK:
        if isinstance(_STATE.get('session'),dict):return dict(_STATE['session'])
    item=_remote_latest(SESSION_KIND)
    if item and isinstance(item.get('payload'),dict):
        p=dict(item['payload']);p['restored_from_remote']=True
        with _LOCK:_STATE['session']=p
        return p
    session={'session_id':f"paper-{int(time.time())}-{(os.getenv('RAILWAY_DEPLOYMENT_ID') or 'local')[:12]}",
             'started_at':_iso(),'origin_sha':(os.getenv('RAILWAY_GIT_COMMIT_SHA') or None),
             'origin_deployment':(os.getenv('RAILWAY_DEPLOYMENT_ID') or None),
             'phase':'AUTONOMOUS_PAPER_LEARNING','simulation_only':True,
             'windows_version':'1.5.28','setup_1_6_allowed':False,
             'automatic_promotion':False,'real_trading':False}
    if persistence.enabled():
        try:persistence.put_snapshot(SESSION_KIND,session,source_max_evaluated_at=None)
        except Exception as exc:
            with _LOCK:_STATE['last_error']=f'{type(exc).__name__}: {str(exc)[:500]}'
    with _LOCK:_STATE['session']=session
    return dict(session)


def _forward_summary():
    try:
        rows=canonical_forward_rows();matured=[r for r in rows if r.get('evaluated_at')]
        return {'rows':len(rows),'matured':len(matured),'source_max_evaluated_at':max((str(r.get('evaluated_at')) for r in matured),default=None)}
    except Exception as exc:return {'rows':None,'matured':None,'error':f'{type(exc).__name__}: {str(exc)[:300]}'}


def simulator_gate(*,technical:dict[str,Any]|None=None,brain:dict[str,Any]|None=None):
    sim=simulator.simulator_status();paper=sim.get('paper') or {};technical=technical or {};brain=brain or {}
    checks={
      'real_trading_frozen': REAL_TRADING is False and sim.get('real_trading') is False,
      'simulator_enabled': sim.get('active') is True,
      'paper_enabled': paper.get('enabled') is True,
      'remote_checkpoint_configured': persistence.enabled(),
      'automatic_live_promotion_blocked': sim.get('automatic_live_promotion') is False,
      'simulation_evidence_separated': sim.get('forward_evidence_mutated') is False,
    }
    if technical:
        checks['operational_health_not_failed']=technical.get('status') not in ('FAILED','CRITICAL')
    blockers=[k for k,v in checks.items() if not v]
    return {'status':'SIMULATOR_READY' if not blockers else 'NOT_READY','checks':checks,'blockers':blockers,
            'brain_readiness_required':False,'positive_alpha_required_to_simulate':False,
            'task_150_required_to_simulate':False,'multi_horizon_maturity_required_to_simulate':False,
            'brain_status':brain.get('status') or brain.get('brain_readiness_gate',{}).get('status'),
            'simulation_only':True,'paper_execution_allowed':not blockers,
            'live_execution_allowed':False,'automatic_promotion':False,'setup_1_6_allowed':False,
            'real_trading':False}


def watchdog_status(cycle_interval_seconds=900):
    sim=simulator.simulator_status();last=sim.get('last_cycle_at');age=_age_seconds(last)
    alerts=[]
    if sim.get('active') is not True:alerts.append('SIMULATOR_PAUSED')
    if sim.get('last_error'):alerts.append('SIMULATOR_ERROR')
    if age is not None and age>max(1800,int(cycle_interval_seconds)*3):alerts.append('SIMULATOR_CYCLE_STALE')
    if last is None:alerts.append('NO_AUTONOMOUS_CYCLE_OBSERVED_YET')
    # Deliberately no per-trade alerts: only operational conditions belong here.
    severity='OK' if not alerts else ('WARMING' if alerts==['NO_AUTONOMOUS_CYCLE_OBSERVED_YET'] else 'ATTENTION')
    with _LOCK:_STATE['alerts']=list(alerts)
    return {'status':severity,'alerts':alerts,'last_cycle_at':last,'last_cycle_age_seconds':age,
            'alert_scope':'OPERATIONAL_ONLY_NO_TRADE_SPAM','real_trading':False}


def _checkpoint_payload():
    sim=simulator.simulator_status();fwd=_forward_summary();paper=sim.get('paper') or {};session=_load_or_create_session()
    return {'session_id':session.get('session_id'),'observed_at':_iso(),'generation':sim.get('generation'),
            'completed_cycles':sim.get('completed_cycles'),'completed_experiments':sim.get('completed_experiments'),
            'last_cycle_at':sim.get('last_cycle_at'),'last_research_at':sim.get('last_research_at'),
            'simulator_status':sim.get('status'),'paper_enabled':paper.get('enabled'),
            'paper_total':paper.get('total'),'paper_cash':paper.get('cash'),'paper_pnl_pct':paper.get('pnl_pct'),
            'forward_rows':fwd.get('rows'),'forward_matured':fwd.get('matured'),
            'source_max_evaluated_at':fwd.get('source_max_evaluated_at'),
            'watchdog':watchdog_status(),'simulation_only':True,'automatic_promotion':False,'real_trading':False}


def persist_checkpoint():
    p=_checkpoint_payload()
    if not persistence.enabled():return {'status':'NOT_CONFIGURED','payload':p,'real_trading':False}
    out=persistence.put_snapshot(CHECKPOINT_KIND,p,source_max_evaluated_at=p.get('source_max_evaluated_at'))
    with _LOCK:
        _STATE['last_checkpoint_epoch']=time.time();_STATE['last_checkpoint_id']=out.get('id');_STATE['last_error']=None
    return {'status':'PERSISTED','id':out.get('id'),'payload':p,'real_trading':False}


def persist_latest_cycle_journal():
    sim=simulator.simulator_status();runs=list(sim.get('recent_runs') or [])
    if not runs:return {'status':'NO_RUNS','real_trading':False}
    run=runs[0];run_id=run.get('run_id')
    with _LOCK:
        if run_id==_STATE.get('last_journal_run_id'):return {'status':'ALREADY_PERSISTED','run_id':run_id,'real_trading':False}
    result=dict(run.get('result') or {});action='PAPER_CYCLE'
    if str(run.get('paper_status')) in ('PAUSED','NOT_CONFIGURED'):action='HOLD'
    payload={'run_id':run_id,'started_at':run.get('started_at'),'completed_at':run.get('completed_at'),
             'generation':run.get('generation'),'status':run.get('status'),'paper_status':run.get('paper_status'),
             'research_status':run.get('research_status'),'action':action,'result':result,
             'journal_includes_non_trade_cycles':True,'simulation_only':True,'real_trading':False}
    if persistence.enabled():persistence.put_snapshot(JOURNAL_KIND,payload,source_max_evaluated_at=None)
    with _LOCK:_STATE['last_journal_run_id']=run_id
    return {'status':'PERSISTED' if persistence.enabled() else 'LOCAL_ONLY','run_id':run_id,'action':action,'real_trading':False}


def milestones():
    session=_load_or_create_session();start=_parse(session.get('started_at'));elapsed=max(0.0,(_utcnow()-start).total_seconds()/3600) if start else 0.0
    targets={'72h':72.0,'7d':168.0,'30d':720.0};out={}
    sim=simulator.simulator_status()
    for name,hours in targets.items():
        reached=elapsed>=hours
        out[name]={'status':'PASS' if reached else 'PENDING_TIME','required_hours':hours,'elapsed_hours':round(elapsed,3),
                   'requires_real_elapsed_time':True,'backfill_allowed':False}
    return {'session_id':session.get('session_id'),'started_at':session.get('started_at'),'elapsed_hours':round(elapsed,3),
            'completed_cycles':sim.get('completed_cycles'),'completed_experiments':sim.get('completed_experiments'),
            'milestones':out,'real_trading':False}


def learning_agenda(brain:dict[str,Any]|None=None):
    """Research agenda for tasks 20-38; proposals only, never automatic promotion."""
    brain=brain or {};tasks=brain.get('tasks') or {}
    net=((tasks.get('355') or {}).get('evidence') or {}).get('mean_net_return')
    abst=((tasks.get('350') or {}).get('state'))
    horizons=((tasks.get('336') or {}).get('evidence') or {})
    return {'priority':'IMPROVE_FORWARD_NET_ALPHA','observed_mean_net_return':net,
      'experiments':[
       {'id':'ENTRY_THRESHOLD','goal':'fewer higher-conviction PAPER entries','forward_promotion':False},
       {'id':'DIRECTION_VS_PROFIT','goal':'separate directional accuracy from cost-adjusted profitability','forward_promotion':False},
       {'id':'HOLDING_DURATION','goal':'estimate PAPER holding-period decay after costs','forward_promotion':False},
       {'id':'UNCERTAINTY_SIZING','goal':'test bounded PAPER sizing by uncertainty','forward_promotion':False},
       {'id':'OPPORTUNITY_COST','goal':'compare candidate with benchmark and skipped alternatives','forward_promotion':False},
       {'id':'WIN_LOSS_ATTRIBUTION','goal':'classify winners and failures without causal overclaim','forward_promotion':False},
       {'id':'SIGNAL_FAMILY_ALPHA','goal':'diagnose cost-adjusted alpha by signal family','forward_promotion':False},
       {'id':'MODEL_DIVERSITY','goal':'incubate genuinely different challengers and penalize correlation','forward_promotion':False},
       {'id':'PIT_REGIME_DIVERSITY','goal':'expand point-in-time regime/sector/asset evidence','forward_promotion':False}],
      'abstention_quality_state':abst,'horizon_maturity':horizons,
      'backtests_role':'HYPOTHESIS_GENERATION_ONLY','historical_can_promote':False,
      'automatic_champion_replacement':False,'real_trading':False}


def dashboard(*,technical=None,brain=None):
    sim=simulator.simulator_status();paper=sim.get('paper') or {};gate=simulator_gate(technical=technical,brain=brain)
    return {'title':'Autonomous Simulator','banner':'SIMULATION ONLY — NO REAL MONEY',
            'gate':gate,'watchdog':watchdog_status(),'session':_load_or_create_session(),'milestones':milestones(),
            'balance':{'total':paper.get('total'),'cash':paper.get('cash'),'invested':paper.get('invested'),'pnl_pct':paper.get('pnl_pct')},
            'simulator':{'status':sim.get('status'),'generation':sim.get('generation'),'completed_cycles':sim.get('completed_cycles'),
                         'completed_experiments':sim.get('completed_experiments'),'last_cycle_at':sim.get('last_cycle_at'),
                         'last_research_at':sim.get('last_research_at'),'last_error':sim.get('last_error')},
            'learning_agenda':learning_agenda(brain),'automatic_promotion':False,'real_trading':False}


def _report_payload(period='daily',brain=None):
    d=dashboard(brain=brain);return {'period':period,'generated_at':_iso(),'dashboard':d,
      'claim':'PAPER_ONLY_OBSERVATIONAL','alerts':d['watchdog']['alerts'],
      'no_trade_notifications':True,'real_trading':False}


def persist_report(period='daily',brain=None):
    p=_report_payload(period,brain);kind=REPORT_WEEKLY_KIND if period=='weekly' else REPORT_DAILY_KIND
    if persistence.enabled():
        out=persistence.put_snapshot(kind,p,source_max_evaluated_at=None);return {'status':'PERSISTED','id':out.get('id'),'report':p,'real_trading':False}
    return {'status':'LOCAL_ONLY','report':p,'real_trading':False}


def _sim_loop():
    simulator.autonomous_simulator_loop(cycle_interval_seconds=900,research_interval_seconds=21600)


def _soak_loop():e2e.soak_loop(interval_seconds=300)


def _control_loop():
    restore_remote_state();_load_or_create_session();last_daily=last_weekly=0.0
    while True:
        try:
            with _LOCK:_STATE['last_supervisor_epoch']=time.time()
            persist_latest_cycle_journal();persist_checkpoint()
            now=time.time()
            if now-last_daily>=86400:persist_report('daily');last_daily=now
            if now-last_weekly>=604800:persist_report('weekly');last_weekly=now
            with _LOCK:_STATE['last_error']=None
        except Exception as exc:
            with _LOCK:_STATE['last_error']=f'{type(exc).__name__}: {str(exc)[:500]}'
            print('[autonomous-paper-control] '+repr(exc),flush=True)
        time.sleep(300)


def _supervisor_loop():
    while True:
        try:
            for name,target in (('simulator',_sim_loop),('soak',_soak_loop),('control',_control_loop)):
                t=_THREADS.get(name)
                if t is None or not t.is_alive():
                    t=threading.Thread(target=target,name='autonomous-paper-'+name,daemon=True);_THREADS[name]=t;t.start()
                    print('[autonomous-paper-supervisor] started '+name,flush=True)
            watchdog_status()
        except Exception as exc:
            with _LOCK:_STATE['last_error']=f'{type(exc).__name__}: {str(exc)[:500]}'
        time.sleep(60)


def ensure_started():
    global _STARTED
    with _LOCK:
        if _STARTED:return control_status()
        _STARTED=True;_STATE['started_epoch']=time.time()
        simulator.set_enabled(True)
        t=threading.Thread(target=_supervisor_loop,name='autonomous-paper-supervisor',daemon=True);_THREADS['supervisor']=t;t.start()
    return control_status()


def control_status():
    with _LOCK:s=dict(_STATE);threads={k:v.is_alive() for k,v in _THREADS.items()}
    s.update({'started':_STARTED,'threads':threads,'persistence':persistence.telemetry(),
              'simulation_only':True,'automatic_promotion':False,'live_execution_allowed':False,
              'windows_version':'1.5.28','setup_1_6_allowed':False,'real_trading':False})
    return s
