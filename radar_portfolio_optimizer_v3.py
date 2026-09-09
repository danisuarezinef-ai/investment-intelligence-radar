"""Survival-first capital competition across cash, existing and new positions."""
from __future__ import annotations
from typing import Any, Iterable

REAL_TRADING = False

def optimize_capital(*, cash: float, equity: float, opportunities: Iterable[dict[str, Any]],
                     max_invested: float=.70, max_position: float=.20, cash_floor: float=.20,
                     drawdown_pct: float | None=None) -> dict[str, Any]:
    if equity <= 0 or cash < 0:
        return {'status':'BLOCKED','reason':'INVALID_ACCOUNT','allocations':[],'can_trade':False,'real_trading':False}
    if drawdown_pct is None:
        return {'status':'BLOCKED','reason':'MISSING_DRAWDOWN_EVIDENCE','allocations':[],'can_trade':False,'real_trading':False}
    risk_multiplier = .5 if drawdown_pct <= -0.07 else 1.0
    if drawdown_pct <= -0.12: risk_multiplier = 0.0
    deploy_cap=max(0.0, min(cash-equity*cash_floor, equity*max_invested))*risk_multiplier
    eligible=[]
    for x in opportunities:
        if x.get('evidence_complete') is not True: continue
        if not isinstance(x.get('expected_return'),(int,float)) or not isinstance(x.get('risk_score'),(int,float)): continue
        utility=float(x['expected_return'])-float(x['risk_score'])
        eligible.append((utility,dict(x)))
    eligible.sort(key=lambda z:z[0], reverse=True)
    allocations=[]; remaining=deploy_cap
    for utility,x in eligible:
        if utility <= 0 or remaining <= 0: break
        amount=min(remaining,equity*max_position)
        allocations.append({'symbol':x['symbol'],'amount':round(amount,2),'utility':utility,'source':'OPTIMIZER_V3'})
        remaining-=amount
    return {'status':'READY' if allocations else 'HOLD_CASH','deployable_capital':round(deploy_cap,2),
            'cash_competes_explicitly':True,'allocations':allocations,'unallocated':round(max(remaining,0),2),
            'objective':'COMPOUND_GROWTH_SUBJECT_TO_SURVIVAL_CONSTRAINTS','optimality_claim':'NOT VERIFIED',
            'can_trade':False,'real_trading':False}
