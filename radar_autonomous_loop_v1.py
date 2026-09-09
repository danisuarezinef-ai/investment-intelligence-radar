"""Autonomous Investment Loop v1 -- shadow/paper governance only.

OBSERVE -> HYPOTHESIZE -> EVIDENCE -> VALUE -> RISK -> COMPARE -> DECIDE ->
ALLOCATE -> OBSERVE OUTCOME -> LEARN -> REASSESS.
No broker integration. No live-capital transition.
"""
from __future__ import annotations

REAL_TRADING=False
STAGES=('OBSERVE','HYPOTHESIZE','EVIDENCE','VALUE','RISK','COMPARE','DECIDE','ALLOCATE','OBSERVE_OUTCOME','LEARN','REASSESS')


def autonomous_cycle(inputs):
    x=inputs or {}
    required=('market_observation','decision_snapshot','allocation_plan','risk_state','shadow_state')
    missing=[k for k in required if x.get(k) is None]
    if missing:
        return {'status':'BLOCKED','reason':'missing_cycle_evidence','missing':missing,
                'completed_stages':[],'next_stage':'OBSERVE','real_trading':False,'can_trade':False}
    if x.get('risk_state',{}).get('blocked') is True:
        return {'status':'BLOCKED','reason':'risk_engine_block','completed_stages':list(STAGES[:5]),
                'next_stage':'REASSESS','real_trading':False,'can_trade':False}
    if x.get('shadow_state',{}).get('started') is not True:
        return {'status':'BLOCKED','reason':'shadow_not_started','completed_stages':list(STAGES[:8]),
                'next_stage':'OBSERVE_OUTCOME','real_trading':False,'can_trade':False}
    matured=bool(x.get('outcome_matured',False))
    completed=list(STAGES[:9] if not matured else STAGES)
    return {'status':'WAITING_OUTCOME' if not matured else 'COMPLETE',
            'completed_stages':completed,
            'next_stage':'OBSERVE_OUTCOME' if not matured else 'OBSERVE',
            'decision_count':len(x.get('allocation_plan',{}).get('approved') or []),
            'learning_applied':False,
            'paper_execution_allowed':bool(x.get('paper_review_approved',False)),
            'live_execution_allowed':False,'can_trade':False,'real_trading':False}
