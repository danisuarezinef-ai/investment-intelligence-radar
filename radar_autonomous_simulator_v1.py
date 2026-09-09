"""Persistent autonomous simulator runtime.

Runs PAPER cycles plus periodic historical research batches without requiring a UI
window. State survives process restarts. Historical/simulated evidence is never
promoted directly to forward evidence or real execution.
"""
from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timezone, timedelta

from radar_core import con, init_db, now, paper_status, paper_start
from radar_simulator_engine_v3 import run_simulator_cycle
from radar_continuous_research_v2 import run_research_batch
from radar_experiment_memory_v2 import memory_snapshot

REAL_TRADING = False
_LOCK = threading.Lock()


def _dt(value):
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def init_autonomous_simulator():
    init_db()
    c = con()
    c.execute('''create table if not exists autonomous_simulator_state(
        id integer primary key check(id=1),
        enabled integer not null default 1,
        status text not null default 'STARTING',
        generation integer not null default 1,
        completed_cycles integer not null default 0,
        completed_experiments integer not null default 0,
        queued_experiments integer not null default 0,
        last_cycle_at text,
        last_research_at text,
        next_cycle_at text,
        next_research_at text,
        last_result text,
        last_error text,
        updated_at text not null
    )''')
    c.execute('''insert or ignore into autonomous_simulator_state(
        id,enabled,status,generation,completed_cycles,completed_experiments,
        queued_experiments,updated_at) values(1,1,'STARTING',1,0,0,0,?)''',(now(),))
    c.commit(); c.close()


def _set(**fields):
    init_autonomous_simulator()
    if not fields:
        return
    fields['updated_at'] = now()
    c = con(); cols = list(fields)
    c.execute('update autonomous_simulator_state set '+','.join(f'{k}=?' for k in cols)+' where id=1',
              [fields[k] for k in cols])
    c.commit(); c.close()


def set_enabled(enabled=True):
    _set(enabled=1 if enabled else 0, status='STARTING' if enabled else 'PAUSED')
    return simulator_status()


def _ensure_paper_active(initial_cash=1000.0):
    st = paper_status()
    if not st.get('configured'):
        paper_start(float(initial_cash))
        return paper_status()
    if not st.get('enabled'):
        # Resume in place: preserve cash, positions, trades and P/L.
        c = con(); c.execute('update paper_account set enabled=1 where id=1'); c.commit(); c.close()
    return paper_status()


def simulator_status():
    init_autonomous_simulator()
    c=con(); r=c.execute('''select enabled,status,generation,completed_cycles,
        completed_experiments,queued_experiments,last_cycle_at,last_research_at,
        next_cycle_at,next_research_at,last_result,last_error,updated_at
        from autonomous_simulator_state where id=1''').fetchone(); c.close()
    try: last_result=json.loads(r[10]) if r and r[10] else None
    except Exception: last_result=None
    paper=paper_status()
    return {
        'active': bool(r[0]) if r else False,
        'status': r[1] if r else 'NOT_CONFIGURED',
        'generation': int(r[2] or 1) if r else 1,
        'completed_cycles': int(r[3] or 0) if r else 0,
        'completed_experiments': int(r[4] or 0) if r else 0,
        'queued_experiments': int(r[5] or 0) if r else 0,
        'last_cycle_at': r[6] if r else None,
        'last_research_at': r[7] if r else None,
        'next_cycle_at': r[8] if r else None,
        'next_research_at': r[9] if r else None,
        'last_result': last_result,
        'last_error': r[11] if r else None,
        'updated_at': r[12] if r else None,
        'paper': {'configured':paper.get('configured',False),'enabled':paper.get('enabled',False),
                  'total':paper.get('total'),'cash':paper.get('cash'),'invested':paper.get('invested'),
                  'pnl_pct':paper.get('pnl_pct')},
        'experiment_memory': memory_snapshot(10),
        'evidence_class':'SIMULATED_HISTORICAL_AND_PAPER_ONLY',
        'forward_evidence_mutated':False,
        'automatic_live_promotion':False,
        'real_trading':False,
    }


def run_autonomous_cycle(*, force_research=False, cycle_interval_seconds=900,
                         research_interval_seconds=21600, initial_cash=1000.0):
    """Run one idempotent autonomous iteration. Safe to invoke after restart."""
    init_autonomous_simulator()
    if not _LOCK.acquire(blocking=False):
        return {'status':'BUSY','real_trading':False}
    try:
        current=simulator_status()
        if not current['active']:
            return {'status':'PAUSED','real_trading':False}
        _set(status='RUNNING', last_error=None)
        paper=_ensure_paper_active(initial_cash)
        cycle=run_simulator_cycle(force=True)
        t=datetime.now(timezone.utc)
        next_cycle=(t+timedelta(seconds=max(60,int(cycle_interval_seconds)))).isoformat()
        generation=current['generation']
        research_due=force_research or not current.get('last_research_at')
        if not research_due:
            last=_dt(current.get('last_research_at'))
            research_due=not last or (t-last).total_seconds()>=max(1800,int(research_interval_seconds))
        research=None; tested=0
        if research_due:
            research=run_research_batch(generation)
            if research.get('status')=='COMPLETED':
                tested=int(research.get('tested') or 0); generation+=1
            next_research=(t+timedelta(seconds=max(1800,int(research_interval_seconds)))).isoformat()
        else:
            next_research=current.get('next_research_at')
        result={'paper_cycle_status':cycle.get('status'),'paper_total':(cycle.get('after') or paper).get('total'),
                'research_status':research.get('status') if research else 'NOT_DUE',
                'experiments_tested':tested,'generation_completed':generation-1 if tested else None,
                'real_trading':False}
        _set(status='ACTIVE',generation=generation,
             completed_cycles=current['completed_cycles']+1,
             completed_experiments=current['completed_experiments']+tested,
             queued_experiments=0,last_cycle_at=t.isoformat(),
             last_research_at=t.isoformat() if research_due else current.get('last_research_at'),
             next_cycle_at=next_cycle,next_research_at=next_research,
             last_result=json.dumps(result,sort_keys=True),last_error=None)
        return {'status':'ACTIVE','result':result,'state':simulator_status(),'real_trading':False}
    except Exception as exc:
        _set(status='DEGRADED_RETRY',last_error=str(exc)[:800],
             next_cycle_at=(datetime.now(timezone.utc)+timedelta(minutes=5)).isoformat())
        return {'status':'DEGRADED_RETRY','error':str(exc)[:800],'real_trading':False}
    finally:
        _LOCK.release()


def autonomous_simulator_loop(cycle_interval_seconds=900,research_interval_seconds=21600):
    """Background daemon; first cycle runs immediately and state persists."""
    init_autonomous_simulator()
    while True:
        state=simulator_status()
        if state['active']:
            result=run_autonomous_cycle(cycle_interval_seconds=cycle_interval_seconds,
                                        research_interval_seconds=research_interval_seconds)
            print('[autonomous-simulator] status={} generation={} cycles={} experiments={} paper={}'.format(
                result.get('status'),simulator_status().get('generation'),
                simulator_status().get('completed_cycles'),simulator_status().get('completed_experiments'),
                simulator_status().get('paper',{}).get('enabled')),flush=True)
        time.sleep(max(60,int(cycle_interval_seconds)))
