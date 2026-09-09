"""Prospective degradation detection v2. Fail-closed and review-only."""
from __future__ import annotations
REAL_TRADING=False

def _f(x):
    try:return float(x)
    except (TypeError,ValueError):return None

def degradation_assessment(reference,current,min_samples=30,hit_drop=0.08,excess_drop_pct=3.0,brier_worsening=0.05):
    reference=reference or {}; current=current or {}
    rn=int(reference.get('samples') or 0); cn=int(current.get('samples') or 0)
    if rn<min_samples or cn<min_samples:
        return {'evidence_complete':False,'degraded':None,'status':'INSUFFICIENT_EVIDENCE','recommended_multiplier':0.5,'real_trading':False}
    rh=_f(reference.get('hit_rate')); ch=_f(current.get('hit_rate')); re=_f(reference.get('excess_return_pct')); ce=_f(current.get('excess_return_pct')); rb=_f(reference.get('brier')); cb=_f(current.get('brier'))
    if None in (rh,ch,re,ce,rb,cb):
        return {'evidence_complete':False,'degraded':None,'status':'INSUFFICIENT_EVIDENCE','recommended_multiplier':0.5,'real_trading':False}
    reasons=[]
    if rh-ch>=hit_drop:reasons.append('hit_rate_degradation')
    if re-ce>=excess_drop_pct:reasons.append('excess_return_degradation')
    if cb-rb>=brier_worsening:reasons.append('calibration_degradation')
    degraded=bool(reasons)
    return {'evidence_complete':True,'degraded':degraded,'status':'DEGRADED' if degraded else 'STABLE','reasons':reasons,
            'recommended_multiplier':0.5 if degraded else 1.0,'automatic_application':False,'real_trading':False}
