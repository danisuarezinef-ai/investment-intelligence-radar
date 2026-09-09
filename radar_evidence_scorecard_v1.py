"""Forward-only evidence scorecard with explicit insufficiency semantics."""
from __future__ import annotations
from datetime import datetime
from math import sqrt
from typing import Any, Iterable

REAL_TRADING=False

def _days(rows:list[dict[str,Any]])->int:
    dates=[]
    for r in rows:
        try:dates.append(datetime.fromisoformat(str(r.get('created_at')).replace('Z','+00:00')))
        except Exception:pass
    return max(0,(max(dates)-min(dates)).days+1) if dates else 0

def scorecard(records: Iterable[dict[str,Any]], *, min_decisions:int=30, min_days:int=14) -> dict[str,Any]:
    rows=[dict(r) for r in records if r.get('matured') is True and r.get('backfilled') is not True]
    returns=[float(r['net_return']) for r in rows if isinstance(r.get('net_return'),(int,float))]
    excess=[float(r['excess_return']) for r in rows if isinstance(r.get('excess_return'),(int,float))]
    briers=[float(r['brier']) for r in rows if isinstance(r.get('brier'),(int,float))]
    hit=[1.0 if float(r['net_return'])>0 else 0.0 for r in rows if isinstance(r.get('net_return'),(int,float))]
    days=_days(rows); n=len(rows)
    benchmark_n=sum(1 for r in rows if isinstance(r.get('benchmark_return'),(int,float)))
    cost_n=sum(1 for r in rows if r.get('cost') is not None)
    benchmark_coverage=benchmark_n/n if n else 0.0;cost_coverage=cost_n/n if n else 0.0
    evidence_complete=(len(returns)>=min_decisions and len(excess)>=min_decisions and benchmark_coverage==1.0 and cost_coverage==1.0)
    sufficient=n>=min_decisions and days>=min_days and evidence_complete
    mean=sum(returns)/len(returns) if returns else None
    vol=(sqrt(sum((x-mean)**2 for x in returns)/(len(returns)-1)) if mean is not None and len(returns)>1 else None)
    blockers=[]
    if n<min_decisions:blockers.append('MIN_MATURE_DECISIONS_NOT_MET')
    if days<min_days:blockers.append('MIN_FORWARD_DAYS_NOT_MET')
    if benchmark_coverage<1.0:blockers.append('BENCHMARK_COVERAGE_INCOMPLETE')
    if cost_coverage<1.0:blockers.append('COST_COVERAGE_INCOMPLETE')
    return {'status':'VERIFIED_FORWARD_SAMPLE' if sufficient else 'INSUFFICIENT_EVIDENCE','matured_decisions':n,
            'forward_days':days,'min_decisions':min_decisions,'min_days':min_days,
            'net_return_observations':len(returns),'excess_return_observations':len(excess),
            'benchmark_coverage':benchmark_coverage,'cost_coverage':cost_coverage,
            'benchmark_and_cost_evidence_complete':evidence_complete,'blockers':blockers,
            'hit_rate':sum(hit)/len(hit) if hit else None,'mean_net_return':mean,'volatility':vol,
            'mean_excess_return':sum(excess)/len(excess) if excess else None,'brier':sum(briers)/len(briers) if briers else None,
            'performance_verified':sufficient,'backfill_used':False,'can_trade':False,'real_trading':False}
