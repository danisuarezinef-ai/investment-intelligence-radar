"""Deterministic PAPER-only accounting for simulator Block D.

Applies fills atomically to an in-memory state, rejects impossible mutations and
is idempotent by fill id. It has no broker or live-order path.
"""
from __future__ import annotations
from copy import deepcopy

REAL_TRADING=False
EPS=1e-9


def new_account(initial_cash: float=100000.0):
    cash=float(initial_cash)
    if cash < 0: raise ValueError('initial_cash_must_be_nonnegative')
    return {'initial_cash':cash,'cash':cash,'positions':{},'realized_pnl':0.0,
            'fees_paid':0.0,'applied_fills':{},'real_trading':False}


def _position(state,symbol):
    return dict((state.get('positions') or {}).get(symbol) or {'qty':0.0,'avg_price':0.0})


def apply_fill(state, *, fill_id, order_id, symbol, side, qty, price, fee=0.0):
    """Return a new state plus result. Duplicate fill_id is a no-op success."""
    s=deepcopy(state or {})
    if s.get('real_trading') is not False: return s,{'status':'REJECTED','reason':'real_trading_state_forbidden','real_trading':False}
    fid=str(fill_id or '').strip(); oid=str(order_id or '').strip(); sym=str(symbol or '').strip().upper(); sd=str(side or '').upper()
    try:q=float(qty); px=float(price); f=max(0.0,float(fee))
    except Exception:return s,{'status':'REJECTED','reason':'invalid_numeric_fill','real_trading':False}
    if not fid or not oid or not sym or sd not in ('BUY','SELL') or q<=0 or px<=0:
        return s,{'status':'REJECTED','reason':'invalid_fill','real_trading':False}
    applied=s.setdefault('applied_fills',{})
    fingerprint=(oid,sym,sd,round(q,12),round(px,12),round(f,12))
    if fid in applied:
        if tuple(applied[fid])==fingerprint:
            return s,{'status':'DUPLICATE_IGNORED','fill_id':fid,'idempotent':True,'real_trading':False}
        return s,{'status':'REJECTED','reason':'fill_id_collision','fill_id':fid,'real_trading':False}
    pos=_position(s,sym); old_qty=float(pos['qty']); old_avg=float(pos['avg_price']); notional=q*px
    if sd=='BUY':
        debit=notional+f
        if float(s.get('cash',0.0))+EPS < debit:
            return s,{'status':'REJECTED','reason':'insufficient_cash','required_cash':debit,'real_trading':False}
        new_qty=old_qty+q; new_avg=((old_qty*old_avg)+(q*px))/new_qty if new_qty>0 else 0.0
        s['cash']=float(s.get('cash',0.0))-debit
        s.setdefault('positions',{})[sym]={'qty':new_qty,'avg_price':new_avg}
        realized_delta=0.0
    else:
        if old_qty+EPS < q:
            return s,{'status':'REJECTED','reason':'insufficient_position','available_qty':old_qty,'real_trading':False}
        realized_delta=(px-old_avg)*q-f
        s['cash']=float(s.get('cash',0.0))+notional-f
        new_qty=max(0.0,old_qty-q)
        if new_qty<=EPS:s.setdefault('positions',{}).pop(sym,None)
        else:s.setdefault('positions',{})[sym]={'qty':new_qty,'avg_price':old_avg}
        s['realized_pnl']=float(s.get('realized_pnl',0.0))+realized_delta
    s['fees_paid']=float(s.get('fees_paid',0.0))+f
    applied[fid]=fingerprint
    s['real_trading']=False
    return s,{'status':'APPLIED','fill_id':fid,'order_id':oid,'symbol':sym,'side':sd,'qty':q,'price':px,
              'fee':f,'realized_pnl_delta':realized_delta,'idempotent':True,'real_trading':False}


def mark_to_market(state, prices):
    s=state or {};prices=prices or {};market_value=0.0;unrealized=0.0;missing=[]
    for sym,p in (s.get('positions') or {}).items():
        if sym not in prices: missing.append(sym);continue
        px=float(prices[sym]);qty=float(p['qty']);avg=float(p['avg_price'])
        market_value+=qty*px;unrealized+=(px-avg)*qty
    cash=float(s.get('cash',0.0));equity=cash+market_value
    return {'cash':cash,'market_value':market_value,'equity':equity,'unrealized_pnl':unrealized,
            'realized_pnl':float(s.get('realized_pnl',0.0)),'fees_paid':float(s.get('fees_paid',0.0)),
            'missing_prices':missing,'equation_error':abs(equity-(cash+market_value)),'real_trading':False}


def accounting_invariants(state, prices):
    mtm=mark_to_market(state,prices)
    positions=state.get('positions') or {}
    nonnegative=all(float(p.get('qty',0))>=-EPS and float(p.get('avg_price',0))>=0 for p in positions.values())
    return {'status':'PASS' if mtm['equation_error']<=EPS and mtm['cash']>=-EPS and nonnegative and not mtm['missing_prices'] else 'FAIL',
            'cash_nonnegative':mtm['cash']>=-EPS,'positions_nonnegative':nonnegative,
            'equation_error':mtm['equation_error'],'missing_prices':mtm['missing_prices'],
            'atomic_fill_accounting':True,'unaccounted_fills':0,'real_trading':False}


def block_d_probes():
    s=new_account(10000.0);results=[]
    s,r=apply_fill(s,fill_id='f1',order_id='o1',symbol='AAA',side='BUY',qty=10,price=100,fee=1);results.append(r)
    before=deepcopy(s);s,r=apply_fill(s,fill_id='f1',order_id='o1',symbol='AAA',side='BUY',qty=10,price=100,fee=1);results.append(r)
    duplicate_preserved=(s==before)
    s,r=apply_fill(s,fill_id='f2',order_id='o2',symbol='BBB',side='BUY',qty=5,price=200,fee=1);results.append(r)
    s,r=apply_fill(s,fill_id='f3',order_id='o3',symbol='AAA',side='SELL',qty=4,price=110,fee=1);results.append(r)
    rejected_cash=apply_fill(s,fill_id='f4',order_id='o4',symbol='CCC',side='BUY',qty=1000,price=1000,fee=1)[1]['status']=='REJECTED'
    rejected_oversell=apply_fill(s,fill_id='f5',order_id='o5',symbol='AAA',side='SELL',qty=999,price=90,fee=1)[1]['status']=='REJECTED'
    inv=accounting_invariants(s,{'AAA':105,'BBB':205})
    return {'status':'PASS' if all(x.get('status') in ('APPLIED','DUPLICATE_IGNORED') for x in results) and duplicate_preserved and rejected_cash and rejected_oversell and inv['status']=='PASS' else 'FAIL',
            'duplicate_retry_no_mutation':duplicate_preserved,'insufficient_cash_rejected':rejected_cash,
            'oversell_rejected':rejected_oversell,'invariants':inv,'results':results,'state':s,
            'broker_connected':False,'live_execution_allowed':False,'real_trading':False}
