"""Autonomous Investment Loop v2 — shadow/paper only.

Runs an observable decision cycle without broker connectivity. It can operate the
paper simulator, freeze prospective paper decisions, inspect v3 shadow evidence,
and evaluate governance gates. It never enables real trading.
"""
from __future__ import annotations
from radar_simulator_engine_v3 import simulator_decision_context, run_simulator_cycle
from radar_paper_portfolio_v4 import freeze_paper_decision, paper_portfolio_v4_status
from radar_paper_to_tiny_live_gate_v1 import paper_to_tiny_live_gate

REAL_TRADING=False
STAGES=('OBSERVE','HYPOTHESIZE','EVIDENCE','VALUE','RISK','COMPARE','DECIDE','ALLOCATE','OUTCOME','LEARN','REASSESS')


def autonomous_loop_v2(*,run_paper=False,promotion_evidence=None,human_approved=False):
    context=simulator_decision_context()
    trace=[]
    for stage in STAGES:
        state='READY'
        if stage in ('OUTCOME','LEARN'):
            state='INSUFFICIENT_EVIDENCE'
        trace.append({'stage':stage,'state':state})
    frozen=None; cycle=None
    if run_paper:
        frozen=freeze_paper_decision({'engine_mode':context.get('mode'),'candidates':context.get('buy_candidates',[]),
                                      'source':'autonomous_loop_v2','backfilled':False})
        cycle=run_simulator_cycle(force=True)
    gate=paper_to_tiny_live_gate(promotion_evidence or {},human_approved=human_approved)
    return {'trace':trace,'decision_context':context,'paper_cycle':cycle,'frozen_decision':frozen,
            'paper_status':paper_portfolio_v4_status(),'tiny_live_gate':gate,
            'execution_mode':'PAPER_ONLY' if run_paper else 'READ_ONLY',
            'broker_connected':False,'live_execution_allowed':False,'can_trade':False,'real_trading':False}
