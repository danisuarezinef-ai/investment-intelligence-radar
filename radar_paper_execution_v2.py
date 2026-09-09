"""Realistic paper execution simulator v2.

Models fills, spread, slippage, partial fills and explicit fees. It is an
in-memory estimator only: no broker integration and no real order path.
"""
from __future__ import annotations

REAL_TRADING = False

DEFAULTS={
    'fee_bps':1.0,
    'spread_bps':4.0,
    'slippage_bps':3.0,
    'max_participation_rate':0.05,
}


def simulate_fill(order, market, assumptions=None):
    a={**DEFAULTS, **(assumptions or {})}
    o=order or {}; m=market or {}
    missing=[k for k in ('side','quantity') if o.get(k) is None]
    missing += [k for k in ('mid_price','available_volume') if m.get(k) is None]
    if missing:
        return {'status':'REJECTED','reason':'missing_execution_evidence','missing':sorted(set(missing)),
                'filled_quantity':0.0,'broker_connected':False,'can_submit_order':False,'real_trading':False}
    side=str(o['side']).upper()
    if side not in ('BUY','SELL'):
        return {'status':'REJECTED','reason':'invalid_side','filled_quantity':0.0,
                'broker_connected':False,'can_submit_order':False,'real_trading':False}
    qty=max(0.0,float(o['quantity'])); mid=float(m['mid_price']); volume=max(0.0,float(m['available_volume']))
    if qty<=0 or mid<=0:
        return {'status':'REJECTED','reason':'invalid_order_or_price','filled_quantity':0.0,
                'broker_connected':False,'can_submit_order':False,'real_trading':False}
    cap=volume*max(0.0,min(1.0,float(a['max_participation_rate'])))
    filled=min(qty,cap)
    if filled<=0:
        return {'status':'UNFILLED','reason':'insufficient_liquidity','side':side,'filled_quantity':0.0,
                'broker_connected':False,'can_submit_order':False,'real_trading':False}
    direction=1.0 if side=='BUY' else -1.0
    impact_bps=(float(a['spread_bps'])/2.0)+float(a['slippage_bps'])
    fill_price=mid*(1.0+direction*impact_bps/10000.0)
    notional=filled*fill_price
    fees=notional*float(a['fee_bps'])/10000.0
    status='FILLED' if filled>=qty else 'PARTIAL'
    return {'status':status,'side':side,'requested_quantity':qty,'filled_quantity':filled,
            'unfilled_quantity':max(0.0,qty-filled),'fill_price':fill_price,'mid_price':mid,
            'notional':notional,'fees':fees,'spread_slippage_bps':impact_bps,
            'participation_rate':(filled/volume if volume else 0.0),
            'execution_assumptions':a,'broker_connected':False,'can_submit_order':False,
            'real_trading':False}


def execution_shortfall_pct(fill):
    f=fill or {}
    if f.get('status') not in ('FILLED','PARTIAL') or not f.get('mid_price'):
        return None
    return abs(float(f['fill_price'])/float(f['mid_price'])-1.0)*100.0
