"""Forward-only evidence scorecard with explicit insufficiency semantics."""
from __future__ import annotations
from math import sqrt
from typing import Any, Iterable

REAL_TRADING=False

def scorecard(records: Iterable[dict[str,Any]], *, min_decisions:int=30) -> dict[str,Any]:
    rows=[dict(r) for r in records if r.get('matured') is True and r.get('backfilled') is not True]
    returns=[float(r['net_return']) for r in rows if isinstance(r.get('net_return'),(int,float))]
    excess=[float(r['excess_return']) for r in rows if isinstance(r.get('excess_return'),(int,float))]
    briers=[float(r['brier']) for r in rows if isinstance(r.get('brier'),(int,float))]
    hit=[1.0 if float(r.get('net_return',0))>0 else 0.0 for r in rows if isinstance(r.get('net_return'),(int,float))]
    sufficient=len(rows)>=min_decisions
    mean=sum(returns)/len(returns) if returns else None
    vol=(sqrt(sum((x-mean)**2 for x in returns)/(len(returns)-1)) if mean is not None and len(returns)>1 else None)
    return {'status':'VERIFIED_FORWARD_SAMPLE' if sufficient else 'INSUFFICIENT_EVIDENCE','matured_decisions':len(rows),
            'hit_rate':sum(hit)/len(hit) if hit else None,'mean_net_return':mean,'volatility':vol,
            'mean_excess_return':sum(excess)/len(excess) if excess else None,'brier':sum(briers)/len(briers) if briers else None,
            'performance_verified':sufficient,'backfill_used':False,'can_trade':False,'real_trading':False}
