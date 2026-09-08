"""Simulation Engine v2: auditable paper/forward simulation and PIT replay. REAL_TRADING is always false."""
from __future__ import annotations
import json, math, statistics, uuid
from datetime import datetime, timezone

from radar_core import con, init_db, now, ASSETS
from radar_agents import AGENTS, agents_status

REAL_TRADING=False


def init_simulation_db():
    init_db(); c=con()
    c.execute('''create table if not exists simulation_runs(
      run_id text primary key,created_at text not null,mode text not null,status text not null,
      start_date text,end_date text,initial_cash real not null,configuration text not null,
      completed_at text,summary text,real_trading integer not null default 0)''')
    c.execute('''create table if not exists simulation_ledger(
      id integer primary key,run_id text not null,ts text not null,agent_id text not null,
      event_type text not null,symbol text,qty real,price real,gross real,costs real,cash real,
      total real,reason text,payload text)''')
    c.execute('''create table if not exists simulation_marks(
      id integer primary key,run_id text not null,ts text not null,agent_id text not null,
      total real not null,cash real not null,invested real not null,benchmark real,
      drawdown_pct real not null default 0)''')
    c.execute('create index if not exists idx_sim_marks_run_agent on simulation_marks(run_id,agent_id,ts)')
    c.execute('create index if not exists idx_sim_ledger_run_agent on simulation_ledger(run_id,agent_id,ts)')
    c.commit(); c.close()


def _metrics(vals, benchmark_vals=None):
    vals=[float(x) for x in vals if x is not None and float(x)>0]
    if not vals:return {'marks':0,'return_pct':0.0,'max_drawdown_pct':0.0,'sharpe':0.0,'sortino':0.0,'benchmark_return_pct':None,'alpha_pct':None}
    peak=vals[0]; max_dd=0.0; rets=[]
    for i,v in enumerate(vals):
        peak=max(peak,v); max_dd=min(max_dd,(v/peak-1)*100 if peak else 0.0)
        if i and vals[i-1]>0:rets.append(v/vals[i-1]-1)
    mean=statistics.mean(rets) if rets else 0.0; sd=statistics.pstdev(rets) if len(rets)>1 else 0.0
    downside=[r for r in rets if r<0]; dsd=statistics.pstdev(downside) if len(downside)>1 else 0.0
    ret=(vals[-1]/vals[0]-1)*100 if vals[0] else 0.0
    bret=None; alpha=None
    if benchmark_vals:
        bs=[float(x) for x in benchmark_vals if x is not None and float(x)>0]
        if len(bs)>=2:bret=(bs[-1]/bs[0]-1)*100; alpha=ret-bret
    return {'marks':len(vals),'return_pct':ret,'max_drawdown_pct':max_dd,'sharpe':(mean/sd*math.sqrt(252) if sd>1e-12 else 0.0),'sortino':(mean/dsd*math.sqrt(252) if dsd>1e-12 else 0.0),'benchmark_return_pct':bret,'alpha_pct':alpha}


def capture_forward_mark(run_id='forward-live'):
    """Append one immutable-like snapshot of all existing paper agents."""
    init_simulation_db(); c=con()
    if not c.execute('select 1 from simulation_runs where run_id=?',(run_id,)).fetchone():
        c.execute('insert into simulation_runs(run_id,created_at,mode,status,initial_cash,configuration,real_trading) values(?,?,?,?,?,?,0)',(run_id,now(),'forward','RUNNING',200.0,json.dumps({'source':'paper_agents','real_trading':False})))
    for st in agents_status():
        if not st.get('configured'):continue
        prior=c.execute('select max(total) from simulation_marks where run_id=? and agent_id=?',(run_id,st['agent_id'])).fetchone()[0]
        peak=max(float(prior or 0),float(st['total'])); dd=(float(st['total'])/peak-1)*100 if peak else 0.0
        c.execute('insert into simulation_marks(run_id,ts,agent_id,total,cash,invested,benchmark,drawdown_pct) values(?,?,?,?,?,?,?,?)',(run_id,now(),st['agent_id'],st['total'],st['cash'],st['invested'],None,dd))
        c.execute('insert into simulation_ledger(run_id,ts,agent_id,event_type,cash,total,reason,payload) values(?,?,?,?,?,?,?,?)',(run_id,now(),st['agent_id'],'MARK',st['cash'],st['total'],'forward paper mark',json.dumps({'positions':st['positions'],'pnl_pct':st['pnl_pct']},sort_keys=True)))
    c.commit(); c.close(); return simulation_summary(run_id)


def _series_by_day(start_date=None,end_date=None):
    init_db(); c=con(); sql='select ts,symbol,price from market_snapshots where price is not null'; args=[]
    if start_date:sql+=' and substr(ts,1,10)>=?';args.append(start_date)
    if end_date:sql+=' and substr(ts,1,10)<=?';args.append(end_date)
    sql+=' order by ts,id'; rows=c.execute(sql,args).fetchall(); c.close()
    days={}
    for ts,s,p in rows:days.setdefault(str(ts)[:10],{})[s]=float(p)
    return [(d,days[d]) for d in sorted(days)]


def _momentum(history,symbol,lookback=20):
    pts=[px[symbol] for _,px in history[-lookback:] if symbol in px]
    return (pts[-1]/pts[0]-1)*100 if len(pts)>=4 and pts[0] else None


def replay_historical(start_date=None,end_date=None,initial_cash=200.0,run_id=None):
    """Point-in-time replay: each decision uses only prices observed before/on that date."""
    init_simulation_db(); run_id=run_id or 'hist-'+uuid.uuid4().hex[:12]; days=_series_by_day(start_date,end_date)
    if len(days)<5:raise ValueError('insufficient historical observations for replay')
    initial_cash=max(50.0,float(initial_cash)); states={aid:{'cash':initial_cash,'pos':{},'peak':initial_cash} for aid in AGENTS}
    first_prices=days[0][1]; benchmark_symbols=[s for s in ASSETS if s in first_prices]; benchmark_units={s:(initial_cash/max(1,len(benchmark_symbols)))/first_prices[s] for s in benchmark_symbols}
    c=con(); c.execute('insert into simulation_runs(run_id,created_at,mode,status,start_date,end_date,initial_cash,configuration,real_trading) values(?,?,?,?,?,?,?,?,0)',(run_id,now(),'historical','RUNNING',days[0][0],days[-1][0],initial_cash,json.dumps({'lookahead':False,'agents':list(AGENTS)},sort_keys=True))); c.commit()
    history=[]
    for day,prices in days:
        history.append((day,prices))
        bench=sum(benchmark_units[s]*prices.get(s,first_prices[s]) for s in benchmark_units)
        for aid,cfg in AGENTS.items():
            st=states[aid]
            # sell: stop-loss or strongly negative 20-session momentum
            for sym in list(st['pos']):
                if sym not in prices:continue
                pos=st['pos'][sym]; pnl=(prices[sym]/pos['avg']-1)*100; mom=_momentum(history,sym,20)
                if pnl<cfg['stop_loss'] or (mom is not None and mom<-5):
                    gross=pos['qty']*prices[sym]; rate=cfg['fee_pct']+cfg['spread_pct']+cfg['fx_pct']; costs=gross*rate; st['cash']+=gross-costs
                    c.execute('insert into simulation_ledger(run_id,ts,agent_id,event_type,symbol,qty,price,gross,costs,cash,reason) values(?,?,?,?,?,?,?,?,?,?,?)',(run_id,day,aid,'SELL',sym,pos['qty'],prices[sym],gross,costs,st['cash'],'PIT stop/risk exit')); del st['pos'][sym]
            ranked=[]
            for sym in ASSETS:
                if sym not in prices or sym in st['pos']:continue
                m20=_momentum(history,sym,20); m60=_momentum(history,sym,60)
                if m20 is None:continue
                score=.65*m20+.35*(m60 if m60 is not None else m20); ranked.append((score,sym))
            ranked.sort(reverse=True)
            invested=sum(p['qty']*prices.get(s,p['avg']) for s,p in st['pos'].items()); total=st['cash']+invested; need=max(0,total*cfg['target_invested']-invested); slots=max(0,cfg['max_positions']-len(st['pos']))
            for score,sym in ranked:
                if slots<=0 or need<8 or st['cash']<10 or score<cfg['min_score']:break
                budget=min(total*cfg['per_position'],need,st['cash']*.96); rate=cfg['fee_pct']+cfg['spread_pct']+cfg['fx_pct']; gross=budget/(1+rate); costs=gross*rate
                if gross<8:continue
                qty=gross/prices[sym]; st['cash']-=gross+costs; st['pos'][sym]={'qty':qty,'avg':prices[sym]}; need-=gross; slots-=1
                c.execute('insert into simulation_ledger(run_id,ts,agent_id,event_type,symbol,qty,price,gross,costs,cash,reason) values(?,?,?,?,?,?,?,?,?,?,?)',(run_id,day,aid,'BUY',sym,qty,prices[sym],gross,costs,st['cash'],f'PIT momentum score {score:.3f}'))
            invested=sum(p['qty']*prices.get(s,p['avg']) for s,p in st['pos'].items()); total=st['cash']+invested; st['peak']=max(st['peak'],total); dd=(total/st['peak']-1)*100 if st['peak'] else 0.0
            c.execute('insert into simulation_marks(run_id,ts,agent_id,total,cash,invested,benchmark,drawdown_pct) values(?,?,?,?,?,?,?,?)',(run_id,day,aid,total,st['cash'],invested,bench,dd))
    c.commit(); summary=simulation_summary(run_id); c.execute('update simulation_runs set status=?,completed_at=?,summary=? where run_id=?',('COMPLETED',now(),json.dumps(summary,sort_keys=True),run_id)); c.commit(); c.close(); return summary


def simulation_summary(run_id='forward-live'):
    init_simulation_db(); c=con(); run=c.execute('select mode,status,start_date,end_date,initial_cash from simulation_runs where run_id=?',(run_id,)).fetchone()
    if not run:c.close(); return {'configured':False,'run_id':run_id,'real_trading':False}
    agents=[]
    for aid in AGENTS:
        rows=c.execute('select total,benchmark from simulation_marks where run_id=? and agent_id=? order by id',(run_id,aid)).fetchall(); vals=[r[0] for r in rows]; bench=[r[1] for r in rows if r[1] is not None]
        trades=c.execute("select count(*),coalesce(sum(costs),0) from simulation_ledger where run_id=? and agent_id=? and event_type in ('BUY','SELL')",(run_id,aid)).fetchone()
        agents.append({'agent_id':aid,'name':AGENTS[aid]['name'],'trades':trades[0],'costs':float(trades[1] or 0),**_metrics(vals,bench)})
    c.close(); champion=max(agents,key=lambda x:(x['alpha_pct'] if x['alpha_pct'] is not None else x['return_pct'])) if agents else None
    return {'configured':True,'run_id':run_id,'mode':run[0],'status':run[1],'start_date':run[2],'end_date':run[3],'initial_cash':run[4],'agents':agents,'leader':champion,'real_trading':False}
