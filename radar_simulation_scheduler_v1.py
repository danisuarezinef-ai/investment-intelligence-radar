"""Autonomous Simulation Lab scheduler contract.

Runs experiment batches only when data/runtime health allows. The caller owns
actual scheduling; this module makes every decision deterministic and auditable.
"""
from __future__ import annotations
from datetime import datetime,timezone
from radar_experiment_brain_v1 import generate_experiments
REAL_TRADING=False


def simulation_cycle(*,history_days=0,cloud_fresh=False,persistence_ok=False,last_run_at=None,generation=1,min_history_days=90,min_interval_hours=6):
    blockers=[]
    if int(history_days)<int(min_history_days):blockers.append('INSUFFICIENT_HISTORY')
    if not cloud_fresh:blockers.append('STALE_CLOUD')
    if not persistence_ok:blockers.append('PERSISTENCE_UNHEALTHY')
    if last_run_at:
        try:
            last=datetime.fromisoformat(str(last_run_at).replace('Z','+00:00'))
            if last.tzinfo is None:last=last.replace(tzinfo=timezone.utc)
            age=(datetime.now(timezone.utc)-last).total_seconds()/3600
            if age<float(min_interval_hours):blockers.append('SIMULATION_INTERVAL_NOT_DUE')
        except Exception:blockers.append('INVALID_LAST_RUN_AT')
    return {'action':'RUN_EXPERIMENT_BATCH' if not blockers else 'HOLD','blockers':blockers,'generation':int(generation),'experiments':generate_experiments(generation) if not blockers else [],'evidence_class':'SIMULATED_HISTORICAL_ONLY','can_promote_directly':False,'real_trading':False}
