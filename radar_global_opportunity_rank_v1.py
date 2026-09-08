"""Global opportunity ranking v1 across comparable Decision Lab cards."""
from __future__ import annotations
from radar_allocation_engine_v1 import opportunity_utility
REAL_TRADING=False

def rank_global_opportunities(cards,metadata_by_symbol=None,limit=25):
    metadata_by_symbol=metadata_by_symbol or {}; ranked=[]; rejected=[]
    for card in cards or []:
        symbol=str((card or {}).get('symbol') or ''); util=opportunity_utility(card)
        meta=metadata_by_symbol.get(symbol) or {}
        complete=all(meta.get(k) is not None for k in ('sector','geography','fx','liquidity_score'))
        if util is None or not complete:
            rejected.append({'symbol':symbol,'reason':'decision_or_risk_metadata_incomplete'}); continue
        ranked.append({'symbol':symbol,'horizon':card.get('horizon'),'action':card.get('action'),'utility':util,
                       'confidence':card.get('confidence'),'expected_return_pct':card.get('expected_return_pct'),
                       'downside_pct':card.get('downside_pct'),'sector':meta.get('sector'),'geography':meta.get('geography'),
                       'fx':meta.get('fx'),'liquidity_score':meta.get('liquidity_score'),'real_trading':False})
    ranked.sort(key=lambda r:(r['utility'],float(r.get('confidence') or 0)),reverse=True)
    for i,r in enumerate(ranked[:max(0,int(limit))],1):r['global_rank']=i
    return {'ranked':ranked[:max(0,int(limit))],'rejected':rejected,'ranking_scope':'all supplied comparable opportunities','can_trade':False,'real_trading':False}
