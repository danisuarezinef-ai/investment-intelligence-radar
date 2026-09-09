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
    risk_multiplier=.5 if drawdown_pct<=-0.07 else 1.0
    if drawdown_pct<=-0.12:risk_multiplier=0.0
    deploy_cap=max(0.0,min(cash-equity*cash_floor,equity*max_invested))*risk_multiplier
    eligible=[]
    for raw in opportunities:
        x=dict(raw)
        # Only prospectively calibrated expected returns may receive new capital.
        if x.get('evidence_complete') is not True:continue
        if x.get('prediction_evidence')!='VERIFIED_FORWARD':continue
        er=x.get('expected_return');risk=x.get('risk_score')
        if not isinstance(er,(int,float)) or not isinstance(risk,(int,float)):continue
        er=float(er);risk=max(0.0,min(1.0,float(risk)))
        if er<=0:continue
        utility=er*(1.0-risk)
        eligible.append((utility,x))
    eligible.sort(key=lambda z:z[0],reverse=True)
    allocations=[];remaining=deploy_cap
    for utility,x in eligible:
        if utility<=0 or remaining<=0:break
        amount=min(remaining,equity*max_position)
        allocations.append({'symbol':x['symbol'],'amount':round(amount,2),'utility':utility,
                            'expected_return':float(x['expected_return']),'risk_score':float(x['risk_score']),
                            'prediction_evidence':'VERIFIED_FORWARD','evidence_complete':True,
                            'source':'OPTIMIZER_V3_FORWARD_GATED'})
        remaining-=amount
    return {'status':'READY' if allocations else 'HOLD_CASH','deployable_capital':round(deploy_cap,2),
            'cash_competes_explicitly':True,'allocations':allocations,'unallocated':round(max(remaining,0),2),
            'objective':'COMPOUND_GROWTH_SUBJECT_TO_SURVIVAL_CONSTRAINTS','optimality_claim':'NOT VERIFIED',
            'evidence_policy':'VERIFIED_FORWARD_ONLY_FOR_NEW_CAPITAL','can_trade':False,'real_trading':False}
