"""Forward Simulation v3.

Closes two audit gaps in v2 forward simulation:
1) imports the actual paper-agent BUY/SELL ledger exactly once;
2) maintains a point-in-time equal-weight benchmark so forward alpha is real,
   rather than implicitly treating a missing benchmark as zero.

Simulation only. REAL_TRADING is hard-disabled.
"""
from __future__ import annotations
import json
from radar_core import con, init_db, now, _latest_prices, ASSETS
from radar_agents import agents_status
from radar_simulation_v2 import init_simulation_db, simulation_summary

REAL_TRADING=False
RUN_ID='forward-live'


def init_forward_v3_db():
    init_simulation_db(); c=con()
    c.execute('''create table if not exists simulation_forward_imports(
      run_id text not null,agent_id text not null,source_trade_id integer not null,imported_at text not null,
      primary key(run_id,agent_id,source_trade_id))''')
    c.execute('''create table if not exists simulation_forward_benchmark(
      run_id text not null,symbol text not null,units real not null,entry_price real not null,created_at text not null,
      primary key(run_id,symbol))''')
    c.commit(); c.close()


def _ensure_run(run_id=RUN_ID):
    init_forward_v3_db(); sts=[x for x in agents_status() if x.get('configured')]
    initial=float(sts[0].get('initial') or 200.0) if sts else 200.0
    c=con()
    if not c.execute('select 1 from simulation_runs where run_id=?',(run_id,)).fetchone():
        c.execute('''insert into simulation_runs(run_id,created_at,mode,status,initial_cash,configuration,real_trading)
                     values(?,?,?,?,?,?,0)''',(run_id,now(),'forward','RUNNING',initial,json.dumps({'source':'paper_agents','benchmark':'equal_weight_available_assets','lookahead':False,'real_trading':False},sort_keys=True)))
        c.commit()
    c.close(); return initial


def _ensure_benchmark(run_id=RUN_ID,initial_cash=None):
    initial_cash=float(initial_cash or _ensure_run(run_id)); prices=_latest_prices(); available=[s for s in ASSETS if prices.get(s) and float(prices[s])>0]
    c=con(); existing=c.execute('select count(*) from simulation_forward_benchmark where run_id=?',(run_id,)).fetchone()[0]
    if not existing and available:
        sleeve=initial_cash/len(available)
        for sym in available:
            px=float(prices[sym]); c.execute('insert into simulation_forward_benchmark(run_id,symbol,units,entry_price,created_at) values(?,?,?,?,?)',(run_id,sym,sleeve/px,px,now()))
        c.commit()
    c.close()


def benchmark_value(run_id=RUN_ID):
    init_forward_v3_db(); prices=_latest_prices(); c=con(); rows=c.execute('select symbol,units,entry_price from simulation_forward_benchmark where run_id=?',(run_id,)).fetchall(); c.close()
    if not rows:return None
    return sum(float(units)*float(prices.get(sym,entry)) for sym,units,entry in rows)


def sync_agent_trades(run_id=RUN_ID):
    """Import each paper-agent trade once into the simulation ledger."""
    _ensure_run(run_id); c=con(); imported=0
    try:
        rows=c.execute('''select id,ts,agent_id,symbol,side,qty,price,gross_value,fees,spread_cost,fx_cost,reason
                          from paper_agent_trades order by id''').fetchall()
    except Exception:
        c.close(); return 0
    for tid,ts,aid,sym,side,qty,price,gross,fees,spread,fx,reason in rows:
        if c.execute('select 1 from simulation_forward_imports where run_id=? and agent_id=? and source_trade_id=?',(run_id,aid,tid)).fetchone():continue
        costs=float(fees or 0)+float(spread or 0)+float(fx or 0)
        c.execute('''insert into simulation_ledger(run_id,ts,agent_id,event_type,symbol,qty,price,gross,costs,reason,payload)
                     values(?,?,?,?,?,?,?,?,?,?,?)''',(run_id,ts,aid,str(side).upper(),sym,qty,price,gross,costs,reason,json.dumps({'source':'paper_agent_trades','source_trade_id':tid},sort_keys=True)))
        c.execute('insert into simulation_forward_imports(run_id,agent_id,source_trade_id,imported_at) values(?,?,?,?)',(run_id,aid,tid,now())); imported+=1
    c.commit(); c.close(); return imported


def capture_forward_mark_v3(run_id=RUN_ID):
    initial=_ensure_run(run_id); _ensure_benchmark(run_id,initial); imported=sync_agent_trades(run_id); bench=benchmark_value(run_id)
    c=con(); stamp=now(); marks=0
    for st in agents_status():
        if not st.get('configured'):continue
        prior=c.execute('select max(total) from simulation_marks where run_id=? and agent_id=?',(run_id,st['agent_id'])).fetchone()[0]
        peak=max(float(prior or 0),float(st['total'])); dd=(float(st['total'])/peak-1)*100 if peak else 0.0
        c.execute('''insert into simulation_marks(run_id,ts,agent_id,total,cash,invested,benchmark,drawdown_pct)
                     values(?,?,?,?,?,?,?,?)''',(run_id,stamp,st['agent_id'],st['total'],st['cash'],st['invested'],bench,dd))
        c.execute('''insert into simulation_ledger(run_id,ts,agent_id,event_type,cash,total,reason,payload)
                     values(?,?,?,?,?,?,?,?)''',(run_id,stamp,st['agent_id'],'MARK',st['cash'],st['total'],'forward paper mark v3',json.dumps({'positions':st['positions'],'pnl_pct':st['pnl_pct'],'benchmark':bench},sort_keys=True)))
        marks+=1
    c.commit(); c.close(); out=simulation_summary(run_id); out['forward_v3']={'trades_imported_this_cycle':imported,'benchmark_value':bench,'marks_written':marks,'lookahead':False}; return out


def simulation_summary_v3(run_id=RUN_ID):
    init_forward_v3_db(); out=simulation_summary(run_id); c=con(); imports=c.execute('select count(*) from simulation_forward_imports where run_id=?',(run_id,)).fetchone()[0]; symbols=c.execute('select count(*) from simulation_forward_benchmark where run_id=?',(run_id,)).fetchone()[0]; c.close(); out['forward_v3']={'imported_trades':imports,'benchmark_symbols':symbols,'benchmark_value':benchmark_value(run_id),'lookahead':False}; return out
