import math, statistics
from radar_core import con, init_db, _daily_series, ASSETS
from radar_agents import AGENTS, init_agents_db

SECONDARY_BENCHMARK='BRK-B'

def _returns(vals):
    out=[]
    for i in range(1,len(vals)):
        if vals[i-1]>0:out.append(vals[i]/vals[i-1]-1.0)
    return out

def _metrics(vals):
    if len(vals)<2:return {'return_pct':0.0,'volatility_pct':0.0,'max_drawdown_pct':0.0,'sharpe':0.0}
    ret=(vals[-1]/vals[0]-1.0)*100.0 if vals[0] else 0.0
    rs=_returns(vals);vol=statistics.pstdev(rs)*math.sqrt(252)*100 if len(rs)>2 else 0.0
    sharpe=(statistics.mean(rs)/statistics.pstdev(rs)*math.sqrt(252)) if len(rs)>3 and statistics.pstdev(rs)>1e-12 else 0.0
    peak=vals[0];mdd=0.0
    for v in vals:
        peak=max(peak,v);mdd=min(mdd,(v/peak-1.0)*100 if peak else 0.0)
    return {'return_pct':ret,'volatility_pct':vol,'max_drawdown_pct':mdd,'sharpe':sharpe}

def _equal_weight_universe(days=365):
    byday={}
    for sym in ASSETS:
        rows=_daily_series(sym,days)
        if len(rows)<2:continue
        base=float(rows[0][1])
        if base<=0:continue
        for day,p in rows:byday.setdefault(day,[]).append(float(p)/base)
    vals=[]
    for day in sorted(byday):
        xs=byday[day]
        if len(xs)>=max(3,len(ASSETS)//3):vals.append(statistics.mean(xs))
    return vals

def benchmark_agents():
    init_db();init_agents_db();c=con();out=[]
    primary_vals=_equal_weight_universe(365);primary=_metrics(primary_vals)
    secondary_vals=[x[1] for x in _daily_series(SECONDARY_BENCHMARK,365)];secondary=_metrics(secondary_vals)
    for aid,cfg in AGENTS.items():
        marks=c.execute('select total from paper_agent_marks where agent_id=? order by id',(aid,)).fetchall();vals=[float(x[0]) for x in marks]
        m=_metrics(vals)
        trades=c.execute('select count(*),coalesce(sum(fees+spread_cost+fx_cost),0) from paper_agent_trades where agent_id=?',(aid,)).fetchone()
        positions=c.execute('select count(*) from paper_agent_positions where agent_id=?',(aid,)).fetchone()[0]
        m.update({'agent_id':aid,'name':cfg['name'],'marks':len(vals),'trades':int(trades[0] or 0),'costs':float(trades[1] or 0),'positions':int(positions or 0),
                  'benchmark':'RADAR_EQUAL_WEIGHT','benchmark_return_pct':primary['return_pct'],'benchmark_sharpe':primary['sharpe'],
                  'excess_return_pct':m['return_pct']-primary['return_pct'],'secondary_benchmark':SECONDARY_BENCHMARK,
                  'secondary_benchmark_return_pct':secondary['return_pct']})
        out.append(m)
    c.close();return sorted(out,key=lambda x:(x['sharpe'],x['excess_return_pct']),reverse=True)
