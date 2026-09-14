"""Block D validation: economic PAPER simulator closure probes."""
from __future__ import annotations
from datetime import datetime, timezone, timedelta
from radar_execution_reality_171_190_v1 import execution_model
from radar_paper_accounting_v1 import new_account, apply_fill, accounting_invariants

REAL_TRADING=False


def _quote(*,bid=99.9,ask=100.1,volume=10000,market_open=True,observed_at=None):
    return {'bid':bid,'ask':ask,'volume':volume,'market_open':market_open,
            'observed_at':observed_at or datetime.now(timezone.utc).isoformat(),'source':'BLOCK_D_CONTROLLED_QUOTE'}


def quote_is_fresh(q,max_age_seconds=120):
    try:
        ts=datetime.fromisoformat(str(q.get('observed_at')).replace('Z','+00:00'))
        if ts.tzinfo is None:ts=ts.replace(tzinfo=timezone.utc)
        return 0 <= (datetime.now(timezone.utc)-ts).total_seconds() <= float(max_age_seconds)
    except Exception:return False


def execute_and_account(state, *, order_id, fill_id, symbol, side, requested_qty, quote, max_age_seconds=120):
    if not quote_is_fresh(quote,max_age_seconds):
        return state,{'status':'REJECTED','reason':'stale_quote','broker_connected':False,'live_execution_allowed':False,'real_trading':False}
    ex=execution_model({'side':side,'requested_qty':requested_qty},quote)
    if ex.get('status') not in ('FILLED','PARTIAL'):
        return state,{**ex,'broker_connected':False,'live_execution_allowed':False,'real_trading':False}
    s=state;applied=[]
    for i,f in enumerate(ex.get('fills') or [],1):
        s,r=apply_fill(s,fill_id=f'{fill_id}:{i}',order_id=order_id,symbol=symbol,side=side,
                       qty=f['qty'],price=f['price'],fee=f.get('fee',0.0))
        if r.get('status') not in ('APPLIED','DUPLICATE_IGNORED'):
            return state,{'status':'REJECTED','reason':'accounting_rejected_fill','accounting':r,
                          'broker_connected':False,'live_execution_allowed':False,'real_trading':False}
        applied.append(r)
    return s,{**ex,'accounting_results':applied,'broker_connected':False,'live_execution_allowed':False,'real_trading':False}


def block_d_validation():
    s=new_account(10000.0)
    # normal buy
    s,buy=execute_and_account(s,order_id='buy-1',fill_id='fill-buy-1',symbol='AAA',side='BUY',requested_qty=10,quote=_quote())
    # duplicate retry must not mutate
    before=repr(s);s2,dup=execute_and_account(s,order_id='buy-1',fill_id='fill-buy-1',symbol='AAA',side='BUY',requested_qty=10,quote=_quote())
    duplicate_ok=repr(s2)==before and any(x.get('status')=='DUPLICATE_IGNORED' for x in dup.get('accounting_results',[]))
    s=s2
    # partial fill: max fill 1% of volume=1 share
    s,partial=execute_and_account(s,order_id='partial-1',fill_id='fill-partial-1',symbol='BBB',side='BUY',requested_qty=10,quote=_quote(volume=100))
    # normal sell
    s,sell=execute_and_account(s,order_id='sell-1',fill_id='fill-sell-1',symbol='AAA',side='SELL',requested_qty=4,quote=_quote(bid=109.9,ask=110.1))
    closed=execute_and_account(s,order_id='closed',fill_id='f-closed',symbol='AAA',side='BUY',requested_qty=1,quote=_quote(market_open=False))[1]
    stale=execute_and_account(s,order_id='stale',fill_id='f-stale',symbol='AAA',side='BUY',requested_qty=1,
                              quote=_quote(observed_at=(datetime.now(timezone.utc)-timedelta(hours=1)).isoformat()))[1]
    illiquid=execute_and_account(s,order_id='liq',fill_id='f-liq',symbol='AAA',side='BUY',requested_qty=1,quote=_quote(volume=0))[1]
    invalid=execute_and_account(s,order_id='bad',fill_id='f-bad',symbol='AAA',side='NOPE',requested_qty=1,quote=_quote())[1]
    inv=accounting_invariants(s,{'AAA':105.0,'BBB':205.0})
    checks={
        'buy_applied':buy.get('status')=='FILLED',
        'duplicate_retry_idempotent':duplicate_ok,
        'partial_fill':partial.get('status')=='PARTIAL' and float(partial.get('remaining_qty') or 0)>0,
        'sell_applied':sell.get('status') in ('FILLED','PARTIAL'),
        'market_closed_rejected':closed.get('reason')=='market_closed',
        'stale_quote_rejected':stale.get('reason')=='stale_quote',
        'insufficient_liquidity_rejected':illiquid.get('reason') in ('insufficient_liquidity','invalid_execution_inputs'),
        'invalid_order_rejected':invalid.get('status')=='REJECTED',
        'cash_equity_identity':inv.get('equation_error')==0,
        'atomic_fill_accounting':inv.get('atomic_fill_accounting') is True and inv.get('unaccounted_fills')==0,
    }
    return {'status':'PASS' if all(checks.values()) else 'FAIL','checks':checks,'accounting':inv,
            'state':s,'broker_connected':False,'live_execution_allowed':False,'real_trading':False}
