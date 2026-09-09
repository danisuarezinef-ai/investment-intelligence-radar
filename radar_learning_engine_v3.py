"""Prospective learning engine v3 by signal, horizon and regime.

Promotion-grade learning requires immutable, matured, non-backfilled, cost-aware and
benchmark-aware forward records. Legacy records that omit the newer evidence flags
remain available only for diagnostic continuity and can never authorize promotion.
"""
from __future__ import annotations
from collections import defaultdict

REAL_TRADING=False
DEFAULT_MIN_SAMPLES=20
DEFAULT_MIN_DAYS=14


def _f(x):
    try:return float(x)
    except (TypeError,ValueError):return None


def _grade(r):
    if not (r.get('immutable') is True and r.get('matured') is True and r.get('backfilled') is not True):return None
    explicit=('cost_aware' in r) or ('benchmark_aware' in r) or ('net_return' in r) or ('excess_return' in r)
    if explicit:
        if r.get('cost_aware') is not True or r.get('benchmark_aware') is not True:return None
        if _f(r.get('net_return')) is None or _f(r.get('excess_return')) is None:return None
        return 'PROMOTION_GRADE'
    if _f(r.get('return_pct')) is not None:return 'LEGACY_DIAGNOSTIC'
    return None


def learn_v3(records,min_samples=DEFAULT_MIN_SAMPLES,min_forward_days=DEFAULT_MIN_DAYS):
    groups=defaultdict(list);eligible_records=0;rejected_records=0;promotion_grade_records=0;legacy_diagnostic_records=0
    for r in records or []:
        grade=_grade(r)
        if not grade:rejected_records+=1;continue
        signals=r.get('signals') if isinstance(r.get('signals'),dict) else {}
        horizon=str(r.get('horizon') or 'UNKNOWN');regime=str(r.get('regime') or 'UNKNOWN')
        if grade=='PROMOTION_GRADE':
            net=_f(r.get('net_return'));excess=_f(r.get('excess_return'));promotion_grade_records+=1
        else:
            net=_f(r.get('return_pct'));excess=net;legacy_diagnostic_records+=1
        eligible_records+=1;day=str(r.get('target_date') or r.get('evaluated_at') or '')[:10]
        for name,value in signals.items():
            v=_f(value)
            if v is not None:groups[(str(name),horizon,regime,grade)].append((v,net,excess,day))
    out=[]
    for (signal,horizon,regime,grade),rows in sorted(groups.items()):
        n=len(rows);days=len({x[3] for x in rows if x[3]})
        days_ok=(days>=min_forward_days) if grade=='PROMOTION_GRADE' else True
        if n<min_samples or not days_ok:
            out.append({'signal':signal,'horizon':horizon,'regime':regime,'samples':n,'forward_days':days,'evidence_grade':grade,'status':'INSUFFICIENT_EVIDENCE','multiplier':1.0,'promotion_eligible':False,'automatic_application':False});continue
        concord=sum(1 for v,_,ex,_ in rows if (v>=0 and ex>=0) or (v<0 and ex<0))/n
        mean_net=sum(x[1] for x in rows)/n;mean_excess=sum(x[2] for x in rows)/n
        multiplier=max(0.75,min(1.25,0.75+0.5*concord))
        out.append({'signal':signal,'horizon':horizon,'regime':regime,'samples':n,'forward_days':days,'evidence_grade':grade,'status':'LEARNED','concordance':concord,'mean_net_return':mean_net,'mean_excess_return':mean_excess,'multiplier':multiplier,'promotion_eligible':grade=='PROMOTION_GRADE','automatic_application':False})
    return {'groups':out,'eligible_records':eligible_records,'promotion_grade_records':promotion_grade_records,'legacy_diagnostic_records':legacy_diagnostic_records,'rejected_records':rejected_records,'minimum_samples':min_samples,'minimum_forward_days':min_forward_days,'automatic_application':False,'real_trading':False}


def recommended_multiplier(learning,signal,horizon,regime):
    for row in (learning or {}).get('groups',[]):
        if row.get('signal')==signal and row.get('horizon')==horizon and row.get('regime')==regime and row.get('status')=='LEARNED' and row.get('promotion_eligible') is True:return float(row.get('multiplier',1.0))
    return 1.0
