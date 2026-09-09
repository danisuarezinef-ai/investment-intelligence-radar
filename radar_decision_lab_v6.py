"""Decision Lab v6: compare investable alternatives and expose opportunity cost."""
from __future__ import annotations

REAL_TRADING = False


def _f(x):
    try: return float(x)
    except (TypeError, ValueError): return None


def _utility(card):
    if not isinstance(card, dict) or card.get('evidence_complete') is not True: return None
    er=_f(card.get('expected_return_pct')); down=_f(card.get('downside_pct')); conf=_f(card.get('confidence')); risk=_f(card.get('risk_score', card.get('valuation_risk')))
    if None in (er,down,conf,risk): return None
    return (er - max(0.0,-down) - max(0.0,risk))*max(0.0,min(1.0,conf))


def decision_lab_v6(cards, allocation=None, risk_results=None):
    allocation = allocation or {}; risk_results = risk_results or {}
    alloc_by_symbol = {str(x.get('symbol')): x for x in allocation.get('allocations') or []}
    rows=[]
    for c in cards or []:
        if not isinstance(c,dict): continue
        symbol=str(c.get('symbol') or '')
        util=_utility(c)
        rr=risk_results.get(symbol) or {}
        blocked=bool(rr.get('blocked')) if rr else False
        final_util=None if util is None else util*float(rr.get('risk_multiplier',1.0) or 0.0)
        rows.append({**c,
            'decision_v6_utility': final_util,
            'risk_blocked': blocked,
            'recommended_budget': _f((alloc_by_symbol.get(symbol) or {}).get('target_budget')) or 0.0,
            'recommended_fraction': _f((alloc_by_symbol.get(symbol) or {}).get('target_fraction')) or 0.0,
            'can_trade':False,'real_trading':False})
    eligible=[r for r in rows if r['decision_v6_utility'] is not None and not r['risk_blocked']]
    eligible.sort(key=lambda r:r['decision_v6_utility'], reverse=True)
    best=eligible[0] if eligible else None
    best_util=best['decision_v6_utility'] if best else None
    for r in rows:
        u=r['decision_v6_utility']
        r['rank']=next((i+1 for i,x in enumerate(eligible) if x.get('symbol')==r.get('symbol')),None)
        r['best_alternative_symbol']=best.get('symbol') if best and best.get('symbol')!=r.get('symbol') else (eligible[1].get('symbol') if len(eligible)>1 else None)
        r['opportunity_cost_utility']=None if u is None or best_util is None else max(0.0,best_util-u)
        if r.get('risk_blocked'): r['action_v6']='AVOID'
        elif r.get('recommended_budget',0)>0: r['action_v6']='BUY'
        elif r.get('action') in ('REDUCE','AVOID'): r['action_v6']=r.get('action')
        else: r['action_v6']='WATCH'
    return {
        'cards': rows,
        'best_symbol': best.get('symbol') if best else None,
        'comparison_count': len(eligible),
        'comparison_note': 'relative utility comparison; NOT empirically validated as optimal',
        'can_trade':False,
        'real_trading':False,
    }
