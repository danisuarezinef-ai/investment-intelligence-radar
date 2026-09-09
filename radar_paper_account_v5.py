"""Paper account v5: append-only prospective account events with cash/position reconstruction."""
from __future__ import annotations
from dataclasses import dataclass
REAL_TRADING=False


def rebuild_account(events, initial_cash):
    cash=float(initial_cash); positions={}; realized=0.0
    for e in events or []:
        if e.get('backfilled') is True: raise ValueError('backfill_forbidden')
        typ=e.get('type'); sym=e.get('symbol'); qty=float(e.get('qty') or 0); price=float(e.get('price') or 0); fees=float(e.get('fees') or 0)
        if typ=='BUY':
            cost=qty*price+fees
            if cost>cash+1e-9: raise ValueError('insufficient_cash')
            old=positions.get(sym,{'qty':0.0,'avg_price':0.0}); newq=old['qty']+qty
            avg=((old['qty']*old['avg_price'])+(qty*price))/newq if newq else 0.0
            positions[sym]={'qty':newq,'avg_price':avg}; cash-=cost
        elif typ=='SELL':
            old=positions.get(sym,{'qty':0.0,'avg_price':0.0})
            if qty>old['qty']+1e-9: raise ValueError('position_underflow')
            cash+=qty*price-fees; realized+=qty*(price-old['avg_price'])-fees
            left=old['qty']-qty
            if left<=1e-12: positions.pop(sym,None)
            else: positions[sym]={'qty':left,'avg_price':old['avg_price']}
        elif typ in ('MARK','OUTCOME','REBALANCE_DECISION'): pass
        else: raise ValueError('unsupported_event')
    return {'cash':cash,'positions':positions,'realized_pnl':realized,'event_count':len(events or []),'real_trading':False}


def append_event(events,event,decision_time=None):
    e=dict(event or {})
    if e.get('backfilled') is True: raise ValueError('backfill_forbidden')
    if decision_time and e.get('ts') and str(e['ts'])<str(decision_time): raise ValueError('event_before_decision_boundary')
    e['backfilled']=False; e['real_trading']=False
    return list(events or [])+[e]
