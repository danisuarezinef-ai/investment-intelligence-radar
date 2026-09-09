"""Forward evidence learning loop v2.
Learns only from matured immutable records and never changes live trading state.
"""
from __future__ import annotations
from collections import defaultdict
REAL_TRADING=False

def _f(x):
    try:return float(x)
    except (TypeError,ValueError):return None

def learn_signal_value(records,min_samples=20):
    buckets=defaultdict(list); rejected=0
    for r in records or []:
        if r.get('immutable') is not True or r.get('matured') is not True or r.get('backfilled') is True:
            rejected+=1; continue
        outcome=_f(r.get('return_pct')); signals=r.get('signals') or {}
        if outcome is None or not isinstance(signals,dict): rejected+=1; continue
        regime=str(r.get('regime') or 'UNKNOWN'); horizon=str(r.get('horizon') or 'UNKNOWN')
        for name,val in signals.items():
            v=_f(val)
            if v is not None:buckets[(str(name),horizon,regime)].append((v,outcome))
    learned=[]
    for (signal,horizon,regime),vals in sorted(buckets.items()):
        n=len(vals)
        if n<min_samples:
            learned.append({'signal':signal,'horizon':horizon,'regime':regime,'samples':n,'status':'INSUFFICIENT_EVIDENCE','weight_multiplier':1.0}); continue
        num=sum(v*o for v,o in vals); den=sum(abs(v) for v,_ in vals) or 1.0
        direction=num/den
        multiplier=max(0.5,min(1.5,1.0+direction/100.0))
        learned.append({'signal':signal,'horizon':horizon,'regime':regime,'samples':n,'status':'EVIDENCE_AVAILABLE','direction_score':direction,'weight_multiplier':multiplier})
    return {'groups':learned,'rejected_records':rejected,'automatic_application':False,'real_trading':False}
