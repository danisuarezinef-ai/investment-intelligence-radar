"""Autonomous self-repair policy for SHADOW/PAPER runtime.

Recovery never fabricates evidence and never enables real trading. It maps observed
failure classes to bounded, idempotent recovery actions and escalation states.
"""
from __future__ import annotations
REAL_TRADING=False

_ACTIONS={
 'STALE_CLOUD':['FREEZE_NEW_PAPER_RISK','REFRESH_MARKET_PROVIDERS','RECHECK_FRESHNESS'],
 'PERSISTENCE_UNHEALTHY':['FREEZE_NEW_PAPER_RISK','PRESERVE_LOCAL_LEDGER','RETRY_PERSISTENCE_SYNC'],
 'FORWARD_INTEGRITY_FAILED':['FREEZE_NEW_PAPER_RISK','QUARANTINE_FORWARD_WRITES','RUN_FORWARD_INTEGRITY_AUDIT'],
 'PAPER_STATE_UNHEALTHY':['FREEZE_NEW_PAPER_RISK','RECONCILE_PAPER_STATE','REVALUE_EXISTING_POSITIONS'],
 'DUPLICATE_EXECUTION_RISK':['FREEZE_NEW_PAPER_RISK','BLOCK_DUPLICATE_IDEMPOTENCY_KEY','RECONCILE_EXECUTION_LEDGER'],
 'PROVIDER_DOWN':['FREEZE_NEW_PAPER_RISK','ROTATE_PROVIDER','APPLY_CIRCUIT_BREAKER','RECHECK_MARKET_COVERAGE'],
 'MISSING_DATA':['FREEZE_NEW_PAPER_RISK','RETRY_DATA_COLLECTION','KEEP_MISSING_AS_MISSING'],
}

def recovery_plan_v2(*,cloud_fresh=True,persistence_ok=True,forward_integrity_ok=True,paper_state_ok=True,duplicate_risk=False,provider_ok=True,missing_data=False,retry_count=0):
    blockers=[]
    if not cloud_fresh:blockers.append('STALE_CLOUD')
    if not persistence_ok:blockers.append('PERSISTENCE_UNHEALTHY')
    if not forward_integrity_ok:blockers.append('FORWARD_INTEGRITY_FAILED')
    if not paper_state_ok:blockers.append('PAPER_STATE_UNHEALTHY')
    if duplicate_risk:blockers.append('DUPLICATE_EXECUTION_RISK')
    if not provider_ok:blockers.append('PROVIDER_DOWN')
    if missing_data:blockers.append('MISSING_DATA')
    actions=[]
    for b in blockers:
        for a in _ACTIONS[b]:
            if a not in actions:actions.append(a)
    if blockers:
        retries=max(0,int(retry_count));delay=min(3600,60*(2**min(retries,6)))
        return {'state':'DEGRADED_HOLD' if retries<6 else 'ESCALATED_HOLD','blockers':blockers,'actions':actions,
                'retry_after_seconds':delay,'can_execute_new_paper':False,'preserve_existing_positions':True,
                'evidence_mutation_allowed':False,'real_trading':False}
    return {'state':'READY','blockers':[],'actions':['RESUME_SHADOW_PAPER_CYCLE'],'retry_after_seconds':0,
            'can_execute_new_paper':True,'preserve_existing_positions':True,'evidence_mutation_allowed':False,'real_trading':False}
