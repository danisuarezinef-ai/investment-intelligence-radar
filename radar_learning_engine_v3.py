"""Prospective learning engine v3 by signal, horizon and regime.

Only immutable, matured, non-backfilled, cost-aware and benchmark-aware forward
records are eligible. Missing evidence stays missing. Nothing is auto-applied.
"""
from __future__ import annotations
from collections import defaultdict

REAL_TRADING=False
DEFAULT_MIN_SAMPLES=20
DEFAULT_MIN_DAYS=14


def _f(x):
    try:return float(x)
    except (TypeError,ValueError):return None


def _eligible_record(r):
    if not (r.get('immutable') is True and r.get('matured') is True and r.get('backfilled') is not True):return False
    if r.get('cost_aware') is not True or r.get('benchmark_aware') is not True:return False
    if _f(r.get('net_return')) is None or _f(r.get('excess_return')) is None:return False
    return True


def learn_v3(records,min_samples=DEFAULT_MIN_SAMPLES,min_forward_days=DEFAULT_MIN_DAYS):
    groups=defaultdict(list); eligible_records=0; rejected_records=0
    for r in records or []:
        if not _eligible_record(r):rejected_records+=1;continue
        signals=r.get('signals') if isinstance(r.get('signals'),dict) else {}
        horizon=str(r.get('horizon') or 'UNKNOWN');regime=str(r.get('regime') or 'UNKNOWN')
        excess=_f(r.get('excess_return'));net=_f(r.get('net_return'))
        if excess is None or net is None:rejected_records+=1;continue
        eligible_records+=1
        day=str(r.get('target_date') or r.get('evaluated_at') or '')[:10]
        for name,value in signals.items():
            v=_f(value)
            if v is not None:groups[(str(name),horizon,regime)].append((v,net,excess,day))
    out=[]
    for (signal,horizon,regime),rows in sorted(groups.items()):
        n=len(rows);days=len({x[3] for x in rows if x[3]})
        if n<min_samples or days<min_forward_days:
            out.append({'signal':signal,'horizon':horizon,'regime':regime,'samples':n,'forward_days':days,
                        'status':'INSUFFICIENT_EVIDENCE','multiplier':1.0,'automatic_application':False});continue
        concord=sum(1 for v,_,ex,_ in rows if (v>=0 and ex>=0) or (v<0 and ex<0))/n
        mean_net=sum(x[1] for x in rows)/n;mean_excess=sum(x[2] for x in rows)/n
        # Bounded research recommendation only. It cannot change production weights by itself.
        multiplier=max(0.75,min(1.25,0.75+0.5*concord))
        out.append({'signal':signal,'horizon':horizon,'regime':regime,'samples':n,'forward_days':days,'status':'LEARNED',
                    'concordance':concord,'mean_net_return':mean_net,'mean_excess_return':mean_excess,
                    'multiplier':multiplier,'automatic_application':False})
    return {'groups':out,'eligible_records':eligible_records,'rejected_records':rejected_records,
            'minimum_samples':min_samples,'minimum_forward_days':min_forward_days,
            'policy_note':'Forward-only cost/benchmark-aware recommendations; multipliers are not auto-applied and optimality is NOT VERIFIED.',
            'automatic_application':False,'real_trading':False}


def recommended_multiplier(learning,signal,horizon,regime):
    for row in (learning or {}).get('groups',[]):
        if row.get('signal')==signal and row.get('horizon')==horizon and row.get('regime')==regime:
            return float(row.get('multiplier',1.0)) if row.get('status')=='LEARNED' else 1.0
    return 1.0
