"""Prospective forward performance engine v1.
Uses only explicit matured forward records. Missing benchmark/cost evidence stays missing.
"""
from __future__ import annotations
import math, statistics
REAL_TRADING=False

def _f(x):
    try:return float(x)
    except (TypeError,ValueError):return None

def forward_performance(records):
    rows=[r for r in (records or []) if r.get('matured') is True and r.get('backfilled') is not True]
    gross=[]; net=[]; excess=[]; probs=[]; outcomes=[]; values=[]
    bench_n=cost_n=0
    for r in rows:
        ret=_f(r.get('return_pct')); cost=_f(r.get('cost_pct')); bench=_f(r.get('benchmark_return_pct'))
        if ret is not None:gross.append(ret)
        if ret is not None and cost is not None:net.append(ret-cost); cost_n+=1
        if ret is not None and bench is not None:excess.append(ret-bench); bench_n+=1
        p=_f(r.get('probability')); y=r.get('positive_outcome')
        if p is not None and y in (0,1,False,True): probs.append(p); outcomes.append(float(bool(y)))
        v=_f(r.get('portfolio_value'))
        if v is not None:values.append(v)
    dd=None
    if values:
        peak=values[0]; worst=0.0
        for v in values:
            peak=max(peak,v)
            if peak>0:worst=min(worst,(v/peak-1.0)*100.0)
        dd=worst
    brier=statistics.mean((p-y)**2 for p,y in zip(probs,outcomes)) if probs else None
    return {
        'matured_records':len(rows),'gross_return_mean_pct':statistics.mean(gross) if gross else None,
        'net_return_mean_pct':statistics.mean(net) if net else None,
        'excess_return_mean_pct':statistics.mean(excess) if excess else None,
        'benchmark_coverage':bench_n/len(rows) if rows else 0.0,
        'cost_coverage':cost_n/len(rows) if rows else 0.0,
        'max_drawdown_pct':dd,'brier_score':brier,
        'performance_verified':bool(rows and gross),'real_trading':False,
        'note':'forward only; no backfill; missing evidence is not coerced to zero'}
