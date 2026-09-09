"""Prospective learning engine v3 by signal, horizon and regime."""
from __future__ import annotations
from collections import defaultdict

REAL_TRADING=False


def _f(x):
    try:return float(x)
    except (TypeError,ValueError):return None


def learn_v3(records,min_samples=20):
    groups=defaultdict(list)
    for r in records or []:
        if not (r.get('immutable') is True and r.get('matured') is True and r.get('backfilled') is not True):continue
        ret=_f(r.get('return_pct'))
        signals=r.get('signals') if isinstance(r.get('signals'),dict) else {}
        if ret is None:continue
        horizon=str(r.get('horizon') or 'UNKNOWN'); regime=str(r.get('regime') or 'UNKNOWN')
        for name,value in signals.items():
            v=_f(value)
            if v is not None:groups[(str(name),horizon,regime)].append((v,ret))
    out=[]
    for (signal,horizon,regime),rows in sorted(groups.items()):
        n=len(rows)
        if n<min_samples:
            out.append({'signal':signal,'horizon':horizon,'regime':regime,'samples':n,'status':'INSUFFICIENT_EVIDENCE','multiplier':1.0,'automatic_application':False});continue
        concord=sum(1 for v,r in rows if (v>=0 and r>=0) or (v<0 and r<0))/n
        avg=sum(r for _,r in rows)/n
        multiplier=max(0.5,min(1.5,0.5+concord))
        out.append({'signal':signal,'horizon':horizon,'regime':regime,'samples':n,'status':'LEARNED','concordance':concord,'mean_return_pct':avg,'multiplier':multiplier,'automatic_application':False})
    return {'groups':out,'policy_note':'Multipliers are heuristic and NOT empirically validated as optimal.','automatic_application':False,'real_trading':False}


def recommended_multiplier(learning,signal,horizon,regime):
    for row in (learning or {}).get('groups',[]):
        if row.get('signal')==signal and row.get('horizon')==horizon and row.get('regime')==regime:return float(row.get('multiplier',1.0))
    return 1.0
