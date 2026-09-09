"""Integrated autonomous investment runtime for SHADOW/PAPER.

The brain may keep learning and proposing improvements indefinitely, while this
runtime keeps execution bounded by observed data, prospective evidence and
risk controls. It can never submit real orders.
"""
from __future__ import annotations
from typing import Any
from radar_autonomy_cycle_v2 import autonomy_decision
from radar_recovery_orchestrator_v1 import recovery_plan
from radar_paper_risk_budget_v2 import assess_risk
from radar_diversification_guard_v1 import diversification_guard
from radar_turnover_cost_governor_v1 import turnover_cost_gate
from radar_paper_authority_v2 import execute_paper_allocations

REAL_TRADING=False


def autonomous_cycle(*, freshness_ok:bool, degraded:bool, promotion_ready:bool,
                     maturity_status:str, paper_authority_ready:bool,
                     persistence_ok:bool, forward_integrity_ok:bool,
                     paper_state_ok:bool, duplicate_risk:bool,
                     account:dict[str,Any], positions:list[dict[str,Any]],
                     drawdown_pct:float|None, allocations:list[dict[str,Any]],
                     prices:dict[str,float], proposed_turnover_pct:float=0.0,
                     estimated_cost_bps:float|None=None,
                     expected_return_bps:float|None=None,
                     pairwise_correlations:list[float]|None=None)->dict[str,Any]:
    recovery=recovery_plan(cloud_fresh=freshness_ok,persistence_ok=persistence_ok,
                           forward_integrity_ok=forward_integrity_ok,paper_state_ok=paper_state_ok,
                           duplicate_risk=duplicate_risk)
    autonomy=autonomy_decision(freshness_ok=freshness_ok,degraded=degraded,
                               promotion_ready=promotion_ready,maturity_status=maturity_status,
                               paper_authority_ready=paper_authority_ready)
    risk=assess_risk(equity=account.get('equity'),cash=account.get('cash'),positions=positions,
                     drawdown_pct=drawdown_pct)
    equity=float(account.get('equity') or 0)
    div_positions=[]
    for p in positions or []:
        mv=float(p.get('market_value') or 0)
        div_positions.append({**p,'weight':(mv/equity if equity>0 else 0.0)})
    diversification=diversification_guard(positions=div_positions,pairwise_correlations=pairwise_correlations)
    turnover=turnover_cost_gate(proposed_turnover_pct=proposed_turnover_pct,
                                estimated_cost_bps=estimated_cost_bps,
                                expected_return_bps=expected_return_bps)
    blockers=[]
    if recovery.get('state')!='READY':blockers.extend(recovery.get('blockers') or [])
    if autonomy.get('action')!='ALLOW_PAPER_CYCLE':blockers.extend(autonomy.get('blockers') or [])
    if risk.get('status')!='PASS_PAPER':blockers.append('PAPER_RISK_BUDGET_BLOCKED')
    if diversification.get('status')!='PASS':blockers.extend(diversification.get('blockers') or [])
    if turnover.get('status')!='PASS':blockers.extend(turnover.get('blockers') or [])
    blockers=sorted(set(blockers))
    governance={'paper_execution_allowed':not blockers,'real_trading':False}
    execution=execute_paper_allocations(governance,allocations,prices) if not blockers else {'status':'HOLD','executed':[],'real_trading':False}
    return {'state':'PAPER_ACTIVE' if not blockers else 'HOLD','blockers':blockers,'recovery':recovery,
            'autonomy':autonomy,'risk':risk,'diversification':diversification,'turnover_cost':turnover,
            'paper_execution':execution,'learning_may_continue':True,'self_improvement_scope':'PROPOSE_TEST_VALIDATE_SHADOW_PAPER',
            'real_order_submission':False,'real_trading':False}
