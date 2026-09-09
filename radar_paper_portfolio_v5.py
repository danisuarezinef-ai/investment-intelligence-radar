"""Persistent PAPER portfolio v5.

Tracks simulated cash, positions, fills, costs, equity snapshots and drawdown.
It never submits real orders and refuses backfilled fills.
"""
from __future__ import annotations
import json,hashlib
from radar_core import con,now

REAL_TRADING=False


def init_paper_v5():
    c=con();cur=c.cursor();cur.executescript('''
    create table if not exists paper_account_v5(
      id integer primary key check(id=1), starting_cash real not null, cash real not null, created_at text not null, updated_at text not null);
    create table if not exists paper_positions_v5(
      symbol text primary key, quantity real not null, avg_cost real not null, updated_at text not null);
    create table if not exists paper_fills_v5(
      id integer primary key autoincrement, created_at text not null, symbol text not null, side text not null,
      quantity real not null, price real not null, gross_value real not null, cost real not null,
      decision_hash text not null unique, backfilled integer not null default 0, real_trading integer not null default 0);
    create table if not exists paper_equity_v5(
      id integer primary key autoincrement, ts text not null, cash real not null, positions_value real not null,
      total real not null, peak real not null, drawdown_pct real not null);
    ''');c.commit();c.close()


def ensure_account(starting_cash=10000.0):
    init_paper_v5();stamp=now();c=con();row=c.execute('select id from paper_account_v5 where id=1').fetchone()
    if not row:c.execute('insert into paper_account_v5 values(1,?,?,?,?)',(float(starting_cash),float(starting_cash),stamp,stamp));c.commit()
    c.close()


def _decision_hash(d):return hashlib.sha256(json.dumps(d,sort_keys=True,separators=(',',':'),default=str).encode()).hexdigest()


def record_fill(*,symbol,side,quantity,price,cost=0.0,decision=None,backfilled=False):
    ensure_account()
    if backfilled:raise ValueError('backfill_not_allowed')
    side=str(side).upper();qty=float(quantity);px=float(price);fee=float(cost)
    if side not in ('BUY','SELL') or qty<=0 or px<=0 or fee<0:raise ValueError('invalid_paper_fill')
    body={'symbol':symbol,'side':side,'quantity':qty,'price':px,'cost':fee,'decision':decision or {},'real_trading':False}
    h=_decision_hash(body);stamp=now();c=con();acct=c.execute('select cash from paper_account_v5 where id=1').fetchone();cash=float(acct[0])
    pos=c.execute('select quantity,avg_cost from paper_positions_v5 where symbol=?',(symbol,)).fetchone();old_q=float(pos[0]) if pos else 0.0;old_cost=float(pos[1]) if pos else 0.0
    gross=qty*px
    if side=='BUY':
        if gross+fee>cash: c.close();raise ValueError('insufficient_paper_cash')
        new_q=old_q+qty;new_avg=((old_q*old_cost)+(qty*px))/new_q;cash-=gross+fee
        c.execute('insert into paper_positions_v5(symbol,quantity,avg_cost,updated_at) values(?,?,?,?) on conflict(symbol) do update set quantity=excluded.quantity,avg_cost=excluded.avg_cost,updated_at=excluded.updated_at',(symbol,new_q,new_avg,stamp))
    else:
        if qty>old_q: c.close();raise ValueError('insufficient_paper_position')
        new_q=old_q-qty;cash+=gross-fee
        if new_q<=1e-12:c.execute('delete from paper_positions_v5 where symbol=?',(symbol,))
        else:c.execute('update paper_positions_v5 set quantity=?,updated_at=? where symbol=?',(new_q,stamp,symbol))
    c.execute('update paper_account_v5 set cash=?,updated_at=? where id=1',(cash,stamp))
    c.execute('insert into paper_fills_v5(created_at,symbol,side,quantity,price,gross_value,cost,decision_hash,backfilled,real_trading) values(?,?,?,?,?,?,?,?,0,0)',(stamp,symbol,side,qty,px,gross,fee,h));c.commit();c.close()
    return {'status':'PAPER_FILL_RECORDED','decision_hash':h,'cash_after':cash,'real_trading':False}


def mark_to_market(prices):
    ensure_account();prices=prices or {};stamp=now();c=con();cash=float(c.execute('select cash from paper_account_v5 where id=1').fetchone()[0]);positions=[];pv=0.0;missing=[]
    for symbol,qty,avg in c.execute('select symbol,quantity,avg_cost from paper_positions_v5 order by symbol').fetchall():
        px=prices.get(symbol)
        if not isinstance(px,(int,float)) or float(px)<=0:missing.append(symbol);continue
        value=float(qty)*float(px);pv+=value;positions.append({'symbol':symbol,'quantity':qty,'avg_cost':avg,'price':float(px),'value':value,'unrealized_pnl':value-float(qty)*float(avg)})
    if missing:c.close();return {'status':'BLOCKED_MISSING_MARKET_PRICES','missing_symbols':missing,'real_trading':False}
    total=cash+pv;prior=c.execute('select max(peak) from paper_equity_v5').fetchone()[0];peak=max(float(prior or total),total);dd=(total/peak-1.0) if peak>0 else 0.0
    c.execute('insert into paper_equity_v5(ts,cash,positions_value,total,peak,drawdown_pct) values(?,?,?,?,?,?)',(stamp,cash,pv,total,peak,dd));c.commit();c.close()
    return {'status':'OK','ts':stamp,'cash':cash,'positions_value':pv,'total':total,'peak':peak,'drawdown_pct':dd,'positions':positions,'real_trading':False}


def paper_portfolio_v5_status():
    ensure_account();c=con();acct=c.execute('select starting_cash,cash,created_at,updated_at from paper_account_v5 where id=1').fetchone();positions=c.execute('select symbol,quantity,avg_cost,updated_at from paper_positions_v5 order by symbol').fetchall();fills=c.execute('select count(*),coalesce(sum(cost),0) from paper_fills_v5').fetchone();eq=c.execute('select ts,total,peak,drawdown_pct from paper_equity_v5 order by id desc limit 1').fetchone();c.close()
    return {'starting_cash':acct[0],'cash':acct[1],'positions':[{'symbol':x[0],'quantity':x[1],'avg_cost':x[2],'updated_at':x[3]} for x in positions],
            'fill_count':fills[0],'costs_paid':fills[1],'equity':({'ts':eq[0],'total':eq[1],'peak':eq[2],'drawdown_pct':eq[3]} if eq else None),
            'performance_claim':'PAPER / NOT VERIFIED','can_trade':False,'real_trading':False}
