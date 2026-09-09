"""Target-value PAPER rebalance engine.

Supports BUY, REDUCE and CLOSE using only the persistent PAPER v5 ledger. Sells are
performed before buys so released fictitious cash is available. No historical fills
or real orders are possible.
"""
from __future__ import annotations
from radar_paper_portfolio_v5 import paper_portfolio_v5_status, record_fill

REAL_TRADING=False


def rebalance_paper(*, governance, target_values, prices, fee_rate=0.001, min_trade_value=1.0):
    if not governance or governance.get('paper_execution_allowed') is not True:
        return {'status':'BLOCKED_BY_PROMOTION_GATE','executed':[],'real_trading':False}
    status=paper_portfolio_v5_status();current={p['symbol']:p for p in status.get('positions',[])}
    targets={str(k):max(0.0,float(v or 0)) for k,v in (target_values or {}).items()}
    executed=[]
    # SELL/REDUCE/CLOSE first.
    for symbol,pos in current.items():
        px=(prices or {}).get(symbol)
        if not isinstance(px,(int,float)) or px<=0:continue
        current_value=float(pos['quantity'])*float(px);target=float(targets.get(symbol,0.0));delta=target-current_value
        if delta>=-float(min_trade_value):continue
        qty=min(float(pos['quantity']),abs(delta)/float(px));fee=qty*float(px)*max(0.0,float(fee_rate))
        action='CLOSE' if target<=float(min_trade_value) else 'REDUCE'
        fill=record_fill(symbol=symbol,side='SELL',quantity=qty,price=float(px),cost=fee,
                         decision={'source':'PAPER_REBALANCE_V1','action':action,'target_value':target},backfilled=False)
        executed.append({'symbol':symbol,'action':action,**fill})
    # Refresh after sales, then BUY increases/new positions.
    current={p['symbol']:p for p in paper_portfolio_v5_status().get('positions',[])}
    for symbol,target in targets.items():
        px=(prices or {}).get(symbol)
        if not isinstance(px,(int,float)) or px<=0:continue
        pos=current.get(symbol);current_value=(float(pos['quantity'])*float(px)) if pos else 0.0;delta=float(target)-current_value
        if delta<=float(min_trade_value):continue
        qty=delta/float(px);fee=delta*max(0.0,float(fee_rate))
        fill=record_fill(symbol=symbol,side='BUY',quantity=qty,price=float(px),cost=fee,
                         decision={'source':'PAPER_REBALANCE_V1','action':'BUY','target_value':target},backfilled=False)
        executed.append({'symbol':symbol,'action':'BUY',**fill})
    return {'status':'PAPER_REBALANCED' if executed else 'NO_CHANGES','executed':executed,
            'automatic_scope':'PAPER_ONLY','backfill_used':False,'can_trade':False,'real_trading':False}
