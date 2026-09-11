"""Multi-window PAPER performance and multidimensional League rankings."""
from __future__ import annotations
from datetime import datetime,timezone,timedelta
import statistics

REAL_TRADING=False


def _dt(x):
    try:
        d=datetime.fromisoformat(str(x).replace('Z','+00:00'));return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:return None

def _f(x,default=None):
    try:return float(x)
    except (TypeError,ValueError):return default


def _window(series,days=None):
    rows=[]
    for r in series or []:
        d=_dt(r.get('date') or r.get('day') or r.get('observed_at'));v=_f(r.get('normalized_equity',r.get('equity')))
        if d and v is not None and v>0:rows.append((d,v))
    rows.sort(key=lambda x:x[0])
    if days is not None and rows:
        cutoff=rows[-1][0]-timedelta(days=int(days));rows=[x for x in rows if x[0]>=cutoff]
    return rows


def _stats(rows):
    if not rows:return {'observed':0,'change_pct':None,'high':None,'low':None,'volatility_pct':None}
    vals=[v for _,v in rows];change=(vals[-1]/vals[0]-1)*100 if len(vals)>=2 and vals[0]>0 else None
    rets=[vals[i]/vals[i-1]-1 for i in range(1,len(vals)) if vals[i-1]>0]
    vol=statistics.pstdev(rets)*100 if len(rets)>=2 else None
    return {'observed':len(rows),'change_pct':change,'high':max(vals),'low':min(vals),'volatility_pct':vol,
            'start':rows[0][0].isoformat(),'end':rows[-1][0].isoformat()}


def multiwindow_performance(series):
    return {'7d':_stats(_window(series,7)),'30d':_stats(_window(series,30)),'90d':_stats(_window(series,90)),
            'since_inception':_stats(_window(series,None)),'backfilled':False,'real_trading':False}


def multidimensional_ranking(strategies,mode='quality'):
    rows=[dict(r) for r in strategies or []]
    def metric(r,name,default=-1e18):
        v=_f(r.get(name));return default if v is None else v
    def score(r):
        if mode=='capital':return metric(r,'current_equity')
        if mode=='v':return metric(r,'v_score')
        if mode=='drawdown':return -abs(metric(r,'max_drawdown_pct',1e18))
        if mode=='consistency':return metric((r.get('v_components') or {}),'consistency')
        if mode=='readiness':return metric(r,'promotion_readiness')
        if mode=='risk_adjusted':return metric((r.get('v_components') or {}),'risk_adjusted_return')
        c=r.get('v_components') or {};return .40*metric(r,'v_score',200)/4+.20*metric(c,'risk_adjusted_return',50)+.20*metric(c,'risk_control',50)+.20*metric(c,'consistency',50)
    ordered=sorted(rows,key=score,reverse=True)
    return {'mode':mode,'ranking':[{'rank':i+1,**r,'ranking_score':score(r)} for i,r in enumerate(ordered)],
            'changes_role':False,'real_trading':False}
