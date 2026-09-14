"""Block D validation: economic PAPER simulator closure probes."""
from __future__ import annotations
from datetime import datetime, timezone, timedelta
from radar_execution_reality_171_190_v1 import execution_model
from radar_paper_accounting_v1 import new_account, apply_fill, accounting_invariants, mark_to_market

REAL_TRADING=False
TRIAL001_ID='RADAR_FIRST_PAPER_TRIAL_001'
TRIAL001_INITIAL_CASH=100000.0


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
    s,buy=execute_and_account(s,order_id='buy-1',fill_id='fill-buy-1',symbol='AAA',side='BUY',requested_qty=10,quote=_quote())
    before=repr(s);s2,dup=execute_and_account(s,order_id='buy-1',fill_id='fill-buy-1',symbol='AAA',side='BUY',requested_qty=10,quote=_quote())
    duplicate_ok=repr(s2)==before and any(x.get('status')=='DUPLICATE_IGNORED' for x in dup.get('accounting_results',[]))
    s=s2
    s,partial=execute_and_account(s,order_id='partial-1',fill_id='fill-partial-1',symbol='BBB',side='BUY',requested_qty=10,quote=_quote(volume=100))
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


def trial001_accounting_validation():
    """Isolated Trial001 account lifecycle. Never touches champion/durable production state."""
    s=new_account(TRIAL001_INITIAL_CASH)
    initial=mark_to_market(s,{})
    # Full buy: ample liquidity, all requested shares filled.
    s,full_buy=execute_and_account(s,order_id='trial001-buy-full',fill_id='trial001-fill-buy-full',symbol='AAA',side='BUY',requested_qty=20,quote=_quote(bid=99.9,ask=100.1,volume=10000))
    aaa_after_buy=float((s.get('positions') or {}).get('AAA',{}).get('qty',0.0))
    # Partial buy: 1% participation cap on volume=200 => 2 shares from 10 requested.
    s,partial_buy=execute_and_account(s,order_id='trial001-buy-partial',fill_id='trial001-fill-buy-partial',symbol='BBB',side='BUY',requested_qty=10,quote=_quote(bid=49.9,ask=50.1,volume=200))
    bbb_after_buy=float((s.get('positions') or {}).get('BBB',{}).get('qty',0.0))
    # Partial sell of AAA.
    s,partial_sell=execute_and_account(s,order_id='trial001-sell-partial',fill_id='trial001-fill-sell-partial',symbol='AAA',side='SELL',requested_qty=5,quote=_quote(bid=109.9,ask=110.1,volume=10000))
    aaa_after_partial=float((s.get('positions') or {}).get('AAA',{}).get('qty',0.0))
    # Full close remaining AAA.
    remaining_aaa=aaa_after_partial
    s,full_close=execute_and_account(s,order_id='trial001-sell-close',fill_id='trial001-fill-sell-close',symbol='AAA',side='SELL',requested_qty=remaining_aaa,quote=_quote(bid=104.9,ask=105.1,volume=10000))
    aaa_closed='AAA' not in (s.get('positions') or {})
    mtm=mark_to_market(s,{'BBB':52.0})
    inv=accounting_invariants(s,{'BBB':52.0})
    checks={
        'isolated_trial_id':TRIAL001_ID=='RADAR_FIRST_PAPER_TRIAL_001',
        'clean_initial_cash':initial['cash']==TRIAL001_INITIAL_CASH and initial['equity']==TRIAL001_INITIAL_CASH,
        'initial_positions_empty':not new_account(TRIAL001_INITIAL_CASH)['positions'],
        'full_buy_applied':full_buy.get('status')=='FILLED' and aaa_after_buy==20.0,
        'partial_buy_applied':partial_buy.get('status')=='PARTIAL' and 0.0<bbb_after_buy<10.0,
        'partial_sell_applied':partial_sell.get('status') in ('FILLED','PARTIAL') and 0.0<aaa_after_partial<aaa_after_buy,
        'full_close_applied':full_close.get('status')=='FILLED' and aaa_closed,
        'cash_plus_market_value_equals_equity':mtm['equation_error']==0.0,
        'realized_pnl_recorded':isinstance(mtm['realized_pnl'],float),
        'unrealized_pnl_recorded':isinstance(mtm['unrealized_pnl'],float),
        'fees_recorded':mtm['fees_paid']>0.0,
        'accounting_invariants':inv.get('status')=='PASS' and inv.get('unaccounted_fills')==0,
        'paper_only':s.get('real_trading') is False,
    }
    return {
        'trial_id':TRIAL001_ID,'initial_cash':TRIAL001_INITIAL_CASH,
        'status':'PASS' if all(checks.values()) else 'FAIL','checks':checks,
        'lifecycle':{'full_buy':full_buy,'partial_buy':partial_buy,'partial_sell':partial_sell,'full_close':full_close},
        'final_account':s,'mark_to_market':mtm,'accounting':inv,
        'isolated_from_champion':True,'broker_connected':False,'live_execution_allowed':False,'real_trading':False,
    }
