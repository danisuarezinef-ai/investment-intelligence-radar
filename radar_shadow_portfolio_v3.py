"""Prospective Shadow Portfolio v3 account state. No broker execution."""
from __future__ import annotations

REAL_TRADING = False


def _f(x, default=0.0):
    try: return float(x)
    except (TypeError, ValueError): return default


def new_shadow_account(initial_cash, started_at):
    cash=_f(initial_cash,-1)
    if cash <= 0 or not started_at:
        return {'valid':False,'reason':'invalid_initial_state','real_trading':False}
    return {'valid':True,'started_at':started_at,'cash':cash,'positions':{},'realized_pnl':0.0,'fees_paid':0.0,'history':[],'real_trading':False}


def rebalance_shadow(account, targets, prices, decision_ts, costs_bps=10.0):
    """Apply a prospective target-weight rebalance using prices known at decision_ts.

    Caller must supply point-in-time prices. Missing price/timestamp evidence blocks the rebalance.
    """
    if not account or not account.get('valid') or not decision_ts:
        return {'applied':False,'reason':'invalid_account_or_time','real_trading':False}
    if decision_ts < str(account.get('started_at')):
        return {'applied':False,'reason':'backfill_forbidden','real_trading':False}
    targets=targets or {}; prices=prices or {}
    if any(_f(w,-1)<0 for w in targets.values()) or sum(_f(w) for w in targets.values()) > 1.000001:
        return {'applied':False,'reason':'invalid_targets','real_trading':False}
    for s in targets:
        p=prices.get(s) or {}
        if _f(p.get('price'),0)<=0 or not p.get('ts') or str(p['ts'])>str(decision_ts):
            return {'applied':False,'reason':'pit_price_missing','symbol':s,'real_trading':False}
    pos=account.get('positions') or {}
    total=account['cash']+sum(_f(v.get('qty'))*_f((prices.get(s) or {}).get('price')) for s,v in pos.items() if s in prices)
    if total<=0: return {'applied':False,'reason':'nonpositive_equity','real_trading':False}
    fee_rate=max(0.0,_f(costs_bps))/10000.0
    newpos={}; turnover=0.0
    for s,w in targets.items():
        px=_f(prices[s]['price']); desired=total*_f(w); current=_f((pos.get(s) or {}).get('qty'))*px
        trade=desired-current; turnover += abs(trade)
        qty=desired/px if px>0 else 0.0
        if qty>0:newpos[s]={'qty':qty,'entry_reference':px,'last_price':px}
    fees=turnover*fee_rate
    cash=max(0.0,total-sum(_f(v['qty'])*_f(prices[s]['price']) for s,v in newpos.items())-fees)
    account['cash']=cash; account['positions']=newpos; account['fees_paid']=_f(account.get('fees_paid'))+fees
    account.setdefault('history',[]).append({'ts':decision_ts,'targets':dict(targets),'turnover':turnover,'fees':fees,'immutable':True,'backfilled':False})
    return {'applied':True,'equity_before_costs':total,'cash':cash,'fees':fees,'turnover':turnover,'positions':newpos,'real_trading':False}


def mark_shadow(account, prices, marked_at):
    if not account or not account.get('valid') or not marked_at:return {'valid':False,'reason':'invalid_mark','real_trading':False}
    market_value=0.0; missing=[]
    for s,p in (account.get('positions') or {}).items():
        q=prices.get(s) or {}; px=_f(q.get('price'),0)
        if px<=0 or not q.get('ts') or str(q['ts'])>str(marked_at):missing.append(s);continue
        market_value += _f(p.get('qty'))*px
    if missing:return {'valid':False,'reason':'mark_price_missing','symbols':missing,'real_trading':False}
    equity=_f(account.get('cash'))+market_value
    return {'valid':True,'marked_at':marked_at,'cash':_f(account.get('cash')),'market_value':market_value,'equity':equity,'fees_paid':_f(account.get('fees_paid')),'real_trading':False}
