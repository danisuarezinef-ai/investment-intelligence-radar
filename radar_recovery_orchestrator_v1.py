"""Autonomous recovery orchestration for SHADOW/PAPER runtime."""
from __future__ import annotations
REAL_TRADING=False


def recovery_plan(*,cloud_fresh=True,persistence_ok=True,forward_integrity_ok=True,paper_state_ok=True,duplicate_risk=False):
    blockers=[]
    if not cloud_fresh:blockers.append('STALE_CLOUD')
    if not persistence_ok:blockers.append('PERSISTENCE_UNHEALTHY')
    if not forward_integrity_ok:blockers.append('FORWARD_INTEGRITY_FAILED')
    if not paper_state_ok:blockers.append('PAPER_STATE_UNHEALTHY')
    if duplicate_risk:blockers.append('DUPLICATE_EXECUTION_RISK')
    if blockers:
        return {'state':'DEGRADED_HOLD','actions':['STOP_NEW_PAPER_ALLOCATIONS','PRESERVE_LEDGER','RETRY_HEALTH_CHECKS'],'blockers':blockers,'can_execute_new_paper':False,'real_trading':False}
    return {'state':'READY','actions':['RESUME_SHADOW_PAPER_CYCLE'],'blockers':[],'can_execute_new_paper':True,'real_trading':False}
