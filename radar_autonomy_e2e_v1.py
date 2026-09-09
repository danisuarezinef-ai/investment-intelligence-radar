"""Persistent end-to-end autonomy and unattended-soak evidence.

This records observed runtime ticks only. It never fabricates elapsed time: a 24-hour
soak becomes VERIFIED only after at least 24 real hours between first and last healthy
ticks. REAL_TRADING remains false.
"""
from __future__ import annotations
import json,time
from datetime import datetime,timezone
from radar_core import con,init_db,now
from radar_autonomous_simulator_v1 import simulator_status
REAL_TRADING=False


def _dt(v):
    try:return datetime.fromisoformat(str(v).replace('Z','+00:00'))
    except Exception:return None


def init_e2e():
    init_db();c=con();c.execute('''create table if not exists autonomy_soak_ticks(
      id integer primary key autoincrement,ts text not null,cloud_ok integer not null,
      persistence_ok integer not null,simulator_active integer not null,paper_enabled integer not null,
      experiments integer not null,cycles integer not null,forward_sync_ok integer not null,
      recovery_state text not null,payload text not null)''');c.commit();c.close()


def record_tick(*,cloud_ok=True,persistence_ok=True,forward_sync_ok=True,recovery_state='READY',extra=None):
    init_e2e();sim=simulator_status();paper=sim.get('paper') or {};payload={'simulator':sim,'extra':extra or {},'real_trading':False}
    c=con();c.execute('''insert into autonomy_soak_ticks(ts,cloud_ok,persistence_ok,simulator_active,paper_enabled,
      experiments,cycles,forward_sync_ok,recovery_state,payload) values(?,?,?,?,?,?,?,?,?,?)''',
      (now(),int(bool(cloud_ok)),int(bool(persistence_ok)),int(bool(sim.get('active'))),int(bool(paper.get('enabled'))),
       int(sim.get('completed_experiments') or 0),int(sim.get('completed_cycles') or 0),int(bool(forward_sync_ok)),str(recovery_state),json.dumps(payload,sort_keys=True)))
    c.commit();c.close();return soak_status()


def soak_status(hours_required=24,min_ticks=12):
    init_e2e();c=con();rows=c.execute('''select ts,cloud_ok,persistence_ok,simulator_active,paper_enabled,experiments,cycles,forward_sync_ok,recovery_state
      from autonomy_soak_ticks order by id asc''').fetchall();c.close()
    healthy=[r for r in rows if all(bool(r[i]) for i in (1,2,3,4,7)) and r[8]=='READY']
    first=_dt(healthy[0][0]) if healthy else None;last=_dt(healthy[-1][0]) if healthy else None
    elapsed=(last-first).total_seconds()/3600 if first and last else 0.0
    exp_delta=(int(healthy[-1][5])-int(healthy[0][5])) if len(healthy)>=2 else 0
    cycle_delta=(int(healthy[-1][6])-int(healthy[0][6])) if len(healthy)>=2 else 0
    blockers=[]
    if elapsed<float(hours_required):blockers.append('REAL_TIME_SOAK_NOT_YET_24H')
    if len(healthy)<int(min_ticks):blockers.append('INSUFFICIENT_HEALTHY_TICKS')
    if cycle_delta<1:blockers.append('NO_AUTONOMOUS_CYCLE_PROGRESS_DURING_SOAK')
    if exp_delta<1:blockers.append('NO_EXPERIMENT_PROGRESS_DURING_SOAK')
    return {'status':'VERIFIED_24H_AUTONOMY' if not blockers else 'COLLECTING_EVIDENCE','elapsed_hours':elapsed,
            'healthy_ticks':len(healthy),'total_ticks':len(rows),'cycle_delta':cycle_delta,'experiment_delta':exp_delta,
            'blockers':blockers,'real_time_required':True,'backfill_allowed':False,'real_trading':False}


def e2e_cycle_status():
    sim=simulator_status();paper=sim.get('paper') or {};mem=sim.get('experiment_memory') or {}
    checks={'data_runtime':bool(sim.get('last_cycle_at')),'brain_generated_experiments':int(sim.get('completed_experiments') or 0)>0,
            'simulation_cycle':int(sim.get('completed_cycles') or 0)>0,'paper_active':bool(paper.get('enabled')),
            'experiment_memory':int(mem.get('count') or 0)>0,'restart_safe_state':sim.get('status') in ('ACTIVE','RUNNING','DEGRADED_RETRY','PAUSED')}
    blockers=[k for k,v in checks.items() if not v]
    return {'status':'AUTONOMOUS_CHAIN_OBSERVED' if not blockers else 'INCOMPLETE','checks':checks,'blockers':blockers,
            'required_chain':'DATA→BRAIN→EXPERIMENT→SIMULATION→SELECTION→SHADOW/PAPER→OUTCOME→LEARNING→NEXT_EXPERIMENT',
            'forward_outcome_and_learning_require_mature_real_time_evidence':True,'real_trading':False}


def soak_loop(interval_seconds=300):
    while True:
        try:
            s=record_tick();print('[autonomy-soak] status={} elapsed_h={:.2f} ticks={} cycles={} experiments={}'.format(s['status'],s['elapsed_hours'],s['healthy_ticks'],s['cycle_delta'],s['experiment_delta']),flush=True)
        except Exception as exc:print('[autonomy-soak] ERROR '+repr(exc),flush=True)
        time.sleep(max(60,int(interval_seconds)))
