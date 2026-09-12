"""Persistent autonomous simulator runtime.

Runs PAPER cycles plus periodic historical research batches without requiring a UI
window. State survives app restarts through the existing persistent authority. Every
autonomous run and every experiment result is auditable. Historical/simulated
evidence never becomes forward evidence or real execution authority.
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
from radar_competitor_explainability_v1 import competitor_live_details

REAL_TRADING=False
_LOCK=threading.Lock()


def _dt(value):
    if not value:return None
    try:
        dt=datetime.fromisoformat(str(value).replace('Z','+00:00'))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:return None


def init_autonomous_simulator():
    init_db();c=con()
    c.execute('''create table if not exists autonomous_simulator_state(
        id integer primary key check(id=1), enabled integer not null default 1,
        status text not null default 'STARTING', generation integer not null default 1,
        completed_cycles integer not null default 0, completed_experiments integer not null default 0,
        queued_experiments integer not null default 0, last_cycle_at text, last_research_at text,
        next_cycle_at text, next_research_at text, last_result text, last_error text, updated_at text not null)''')
    c.execute('''create table if not exists autonomous_simulator_runs(
        run_id integer primary key, started_at text not null, completed_at text,
        generation integer not null, status text not null, paper_status text,
        research_status text, result_json text, evidence_class text not null,
        real_trading integer not null default 0)''')
    c.execute('''create table if not exists autonomous_experiment_results(
        id integer primary key, run_id integer not null, generation integer not null,
        experiment_id text not null, configuration text not null, result_json text not null,
        gate_status text, research_score real, stage text not null, created_at text not null,
        real_trading integer not null default 0,
        unique(run_id,experiment_id))''')
    c.execute('''insert or ignore into autonomous_simulator_state(
        id,enabled,status,generation,completed_cycles,completed_experiments,
        queued_experiments,updated_at) values(1,1,'STARTING',1,0,0,0,?)''',(now(),))
    c.execute("update autonomous_simulator_runs set status='INTERRUPTED_RESTART',completed_at=? where status='RUNNING'",(now(),))
    c.commit();c.close()


def _set(**fields):
    init_autonomous_simulator()
    if not fields:return
    fields['updated_at']=now();c=con();cols=list(fields)
    c.execute('update autonomous_simulator_state set '+','.join(f'{k}=?' for k in cols)+' where id=1',[fields[k] for k in cols]);c.commit();c.close()


def set_enabled(enabled=True):
    _set(enabled=1 if enabled else 0,status='STARTING' if enabled else 'PAUSED');return simulator_status()


def _ensure_paper_active(initial_cash=1000.0):
    st=paper_status()
    if not st.get('configured'):
        paper_start(float(initial_cash));return paper_status()
    if not st.get('enabled'):
        c=con();c.execute('update paper_account set enabled=1 where id=1');c.commit();c.close()
    return paper_status()


def _open_run(generation):
    c=con();ts=now();cur=c.execute('''insert into autonomous_simulator_runs(
        started_at,generation,status,evidence_class,real_trading) values(?,?,'RUNNING','SIMULATED_HISTORICAL_AND_PAPER_ONLY',0)''',(ts,int(generation)));run_id=cur.lastrowid;c.commit();c.close();return run_id,ts


def _finish_run(run_id,*,status,paper_status=None,research_status=None,result=None):
    c=con();c.execute('''update autonomous_simulator_runs set completed_at=?,status=?,paper_status=?,research_status=?,result_json=?,real_trading=0 where run_id=?''',
        (now(),status,paper_status,research_status,json.dumps(result or {},sort_keys=True,default=str),int(run_id)));c.commit();c.close()


def _persist_experiments(run_id,generation,research):
    rows=list((research or {}).get('results') or []);c=con();saved=0
    for row in rows:
        cfg=row.get('configuration') or {};gate=row.get('gate') or {};gate_status=gate.get('status') or 'NOT_VERIFIED'
        stage='SHADOW_REVIEW' if gate_status=='PASS_RESEARCH' else 'GRAVEYARD'
        try:
            c.execute('''insert or ignore into autonomous_experiment_results(
                run_id,generation,experiment_id,configuration,result_json,gate_status,research_score,stage,created_at,real_trading)
                values(?,?,?,?,?,?,?,?,?,0)''',(int(run_id),int(generation),str(row.get('experiment_id') or ''),json.dumps(cfg,sort_keys=True),json.dumps(row,sort_keys=True,default=str),gate_status,row.get('research_score'),stage,now()))
            saved+=c.rowcount
        except Exception:continue
    c.commit();c.close();return saved


def _recent_runs(limit=10):
    c=con();rows=c.execute('''select run_id,started_at,completed_at,generation,status,paper_status,research_status,result_json
        from autonomous_simulator_runs order by run_id desc limit ?''',(max(1,min(int(limit),50)),)).fetchall();c.close();out=[]
    for r in rows:
        try:result=json.loads(r[7] or '{}')
        except Exception:result={}
        out.append({'run_id':r[0],'started_at':r[1],'completed_at':r[2],'generation':r[3],'status':r[4],'paper_status':r[5],'research_status':r[6],'result':result})
    return out


def _recent_experiments(limit=20):
    c=con();rows=c.execute('''select run_id,generation,experiment_id,configuration,gate_status,research_score,stage,created_at
        from autonomous_experiment_results order by id desc limit ?''',(max(1,min(int(limit),100)),)).fetchall();c.close();out=[]
    for r in rows:
        try:cfg=json.loads(r[3] or '{}')
        except Exception:cfg={}
        out.append({'run_id':r[0],'generation':r[1],'experiment_id':r[2],'configuration':cfg,'gate_status':r[4],'research_score':r[5],'stage':r[6],'created_at':r[7]})
    return out


def _competitor_details_fail_soft():
    try:return competitor_live_details()
    except Exception as exc:
        return {'status':'DEGRADED','error':str(exc)[:500],'source':'LIVE_LOCAL_PAPER_ENGINE_READ_ONLY','competitors':{},
                'durable_authority':False,'automatic_model_promotion':False,'live_execution_allowed':False,
                'can_trade':False,'real_trading':False}


def simulator_status():
    init_autonomous_simulator();c=con();r=c.execute('''select enabled,status,generation,completed_cycles,
        completed_experiments,queued_experiments,last_cycle_at,last_research_at,next_cycle_at,next_research_at,
        last_result,last_error,updated_at from autonomous_simulator_state where id=1''').fetchone();c.close()
    try:last_result=json.loads(r[10]) if r and r[10] else None
    except Exception:last_result=None
    paper=paper_status();runs=_recent_runs(10);experiments=_recent_experiments(20);competitors=_competitor_details_fail_soft()
    return {'active':bool(r[0]) if r else False,'status':r[1] if r else 'NOT_CONFIGURED','generation':int(r[2] or 1) if r else 1,
        'completed_cycles':int(r[3] or 0) if r else 0,'completed_experiments':int(r[4] or 0) if r else 0,'queued_experiments':int(r[5] or 0) if r else 0,'last_cycle_at':r[6] if r else None,'last_research_at':r[7] if r else None,
        'next_cycle_at':r[8] if r else None,'next_research_at':r[9] if r else None,'last_result':last_result,
        'last_error':r[11] if r else None,'updated_at':r[12] if r else None,
        'paper':{'configured':paper.get('configured',False),'enabled':paper.get('enabled',False),'total':paper.get('total'),'cash':paper.get('cash'),'invested':paper.get('invested'),'pnl_pct':paper.get('pnl_pct')},
        'competitor_details':competitors,'recent_runs':runs,'recent_experiments':experiments,'experiment_memory':memory_snapshot(10),
        'evidence_class':'SIMULATED_HISTORICAL_AND_PAPER_ONLY','forward_evidence_mutated':False,
        'automatic_live_promotion':False,'real_trading':False}


def _decision_class(cycle):
    status=str((cycle or {}).get('status') or '')
    context=(cycle or {}).get('context') or {};candidates=list(context.get('buy_candidates') or [])
    if status in ('PAUSED','NOT_CONFIGURED'):return 'HOLD'
    if not candidates:return 'ABSTAIN_NO_CANDIDATE'
    return 'PAPER_CYCLE_WITH_CANDIDATES'


def run_autonomous_cycle(*,force_research=False,cycle_interval_seconds=900,research_interval_seconds=21600,initial_cash=1000.0):
    init_autonomous_simulator()
    if not _LOCK.acquire(blocking=False):return {'status':'BUSY','real_trading':False}
    run_id=None
    try:
        current=simulator_status()
        if not current['active']:return {'status':'PAUSED','real_trading':False}
        run_id,_=_open_run(current['generation']);_set(status='RUNNING',last_error=None)
        paper=_ensure_paper_active(initial_cash);cycle=run_simulator_cycle(force=True);context=dict(cycle.get('context') or {});t=datetime.now(timezone.utc)
        next_cycle=(t+timedelta(seconds=max(60,int(cycle_interval_seconds)))).isoformat();generation=current['generation']
        research_due=force_research or not current.get('last_research_at')
        if not research_due:
            last=_dt(current.get('last_research_at'));research_due=not last or (t-last).total_seconds()>=max(1800,int(research_interval_seconds))
        research=None;tested=0;saved=0
        if research_due:
            _set(queued_experiments=6);research=run_research_batch(generation);tested=int(research.get('tested') or 0)
            saved=_persist_experiments(run_id,generation,research)
            if research.get('status')=='COMPLETED':generation+=1
            next_research=(t+timedelta(seconds=max(1800,int(research_interval_seconds)))).isoformat()
        else:next_research=current.get('next_research_at')
        result={'run_id':run_id,'paper_cycle_status':cycle.get('status'),'decision_class':_decision_class(cycle),
            'decision_context':context,'paper_total':(cycle.get('after') or paper).get('total'),
            'research_status':research.get('status') if research else 'NOT_DUE','experiments_tested':tested,
            'experiment_results_persisted':saved,'generation_completed':generation-1 if tested else None,
            'journal_includes_hold_abstain_and_candidate_cycles':True,'real_trading':False}
        _finish_run(run_id,status='COMPLETED',paper_status=cycle.get('status'),research_status=result['research_status'],result=result)
        _set(status='ACTIVE',generation=generation,completed_cycles=current['completed_cycles']+1,
            completed_experiments=current['completed_experiments']+tested,queued_experiments=0,last_cycle_at=t.isoformat(),
            last_research_at=t.isoformat() if research_due else current.get('last_research_at'),next_cycle_at=next_cycle,next_research_at=next_research,
            last_result=json.dumps(result,sort_keys=True),last_error=None)
        return {'status':'ACTIVE','result':result,'state':simulator_status(),'real_trading':False}
    except Exception as exc:
        if run_id is not None:_finish_run(run_id,status='FAILED',result={'error':str(exc)[:800],'real_trading':False})
        _set(status='DEGRADED_RETRY',queued_experiments=0,last_error=str(exc)[:800],next_cycle_at=(datetime.now(timezone.utc)+timedelta(minutes=5)).isoformat())
        return {'status':'DEGRADED_RETRY','error':str(exc)[:800],'real_trading':False}
    finally:_LOCK.release()


def autonomous_simulator_loop(cycle_interval_seconds=900,research_interval_seconds=21600):
    init_autonomous_simulator()
    while True:
        state=simulator_status()
        if state['active']:
            result=run_autonomous_cycle(cycle_interval_seconds=cycle_interval_seconds,research_interval_seconds=research_interval_seconds)
            s=simulator_status();print('[autonomous-simulator] status={} generation={} cycles={} experiments={} paper={}'.format(result.get('status'),s.get('generation'),s.get('completed_cycles'),s.get('completed_experiments'),s.get('paper',{}).get('enabled')),flush=True)
        time.sleep(max(60,int(cycle_interval_seconds)))
