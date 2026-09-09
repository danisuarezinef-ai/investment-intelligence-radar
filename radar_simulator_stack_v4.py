"""Simulator stack v4.
Uses the current Decision/Risk/Allocation stack when evidence is complete and a clearly
labelled heuristic simulation fallback otherwise. Never enables live execution.
"""
from __future__ import annotations
from radar_investment_stack_v2 import integrated_investment_stack_v2
REAL_TRADING=False

def run_simulator_cycle(cards,portfolio,metadata_by_symbol=None,correlations=None,regime=None,heuristic_fallback=None):
    stack=integrated_investment_stack_v2(cards,portfolio,metadata_by_symbol,correlations,regime)
    allocs=(stack.get('allocation') or {}).get('allocations') or []
    if allocs:
        mode='VERIFIED_STACK'; decisions=stack.get('decisions') or []
    else:
        mode='SIMULATION_ONLY_HEURISTIC'
        decisions=[]
        for row in heuristic_fallback or []:
            r=dict(row); r['simulation_only']=True; r['real_trading']=False; decisions.append(r)
    return {'mode':mode,'stack':stack,'simulated_decisions':decisions,
            'live_execution_allowed':False,'can_trade':False,'real_trading':False}
