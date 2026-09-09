"""Simulator engine v3.

Keeps production decision gates fail-closed while allowing the PAPER simulator to
continue experimenting with clearly labelled heuristic decisions when verified
Decision Lab evidence is not yet complete. No broker path exists.
"""
from __future__ import annotations

from radar_core import opportunity_rankings, paper_status, paper_step
from radar_decision_lab_v5 import decision_lab_v5_snapshot

REAL_TRADING=False


def simulator_decision_context():
    snap=decision_lab_v5_snapshot(limit=20)
    buys=[c for c in snap.get('cards',[]) if c.get('action')=='BUY' and c.get('evidence_complete') is True]
    if buys:
        return {'mode':'VERIFIED_DECISION_CARDS','buy_candidates':[c.get('symbol') for c in buys],
                'fallback_used':False,'performance_claim':'NOT VERIFIED','real_trading':False}
    ranks=opportunity_rankings(8)
    heuristic=[]
    for tier in ('bajo','intermedio','alto'):
        for row in ranks.get(tier,[]):
            if float(row.get('score') or 0)>0:
                heuristic.append({'symbol':row.get('symbol'),'score':row.get('score'),'risk':tier})
    heuristic.sort(key=lambda x:float(x.get('score') or 0),reverse=True)
    return {'mode':'SIMULATION_ONLY_HEURISTIC','buy_candidates':[x['symbol'] for x in heuristic[:5]],
            'fallback_used':True,
            'reason':'Decision Lab evidence incomplete; paper simulator may explore heuristics without weakening live gates',
            'performance_claim':'SIMULATED / NOT VERIFIED','real_trading':False}


def run_simulator_cycle(force=True):
    before=paper_status()
    if not before.get('configured'):
        return {'status':'NOT_CONFIGURED','before':before,'after':before,'context':simulator_decision_context(),
                'can_trade':False,'real_trading':False}
    if not before.get('enabled'):
        return {'status':'PAUSED','before':before,'after':before,'context':simulator_decision_context(),
                'can_trade':False,'real_trading':False}
    context=simulator_decision_context()
    after=paper_step(force=force)
    return {'status':'OK','before':before,'after':after,'context':context,
            'paper_execution_only':True,'can_trade':False,'real_trading':False}
