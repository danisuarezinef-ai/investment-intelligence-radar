"""Forward-only champion/challenger governance.

Historical, simulated, backfilled or benchmark-incomplete evidence cannot promote a
model. Automatic replacement remains disabled; this module only recommends changes
inside SHADOW/PAPER governance.
"""
from __future__ import annotations
from datetime import datetime
from typing import Any, Iterable
REAL_TRADING=False


def _eligible(m:dict[str,Any],min_forward_n:int,min_forward_days:int)->bool:
    n=int(m.get('forward_n') or 0);days=int(m.get('forward_days') or 0)
    return (
        n>=min_forward_n and days>=min_forward_days and
        m.get('backfilled') is not True and m.get('forward_only') is True and
        m.get('cost_aware') is True and m.get('benchmark_aware') is True and
        m.get('matured_only') is True and
        isinstance(m.get('mean_excess_return'),(int,float))
    )


def derive_forward_model_metrics(records:Iterable[dict[str,Any]])->list[dict[str,Any]]:
    groups:dict[str,list[dict[str,Any]]]={}
    for raw in records:
        r=dict(raw)
        if r.get('matured') is not True or r.get('backfilled') is True:continue
        model=str(r.get('model_version') or '').strip()
        if not model:continue
        groups.setdefault(model,[]).append(r)
    out=[]
    for model,rows in groups.items():
        excess=[float(r['excess_return']) for r in rows if isinstance(r.get('excess_return'),(int,float))]
        dates=[]
        for r in rows:
            try:dates.append(datetime.fromisoformat(str(r.get('created_at')).replace('Z','+00:00')))
            except Exception:pass
        days=max(0,(max(dates)-min(dates)).days+1) if dates else 0
        out.append({'model_version':model,'forward_n':len(rows),'forward_days':days,
                    'mean_excess_return':sum(excess)/len(excess) if excess else None,
                    'forward_only':True,'matured_only':True,'backfilled':False,
                    'benchmark_aware':len(excess)==len(rows) and len(rows)>0,
                    'cost_aware':all(r.get('cost') is not None for r in rows),
                    'can_trade':False,'real_trading':False})
    return out


def compete(models:Iterable[dict[str,Any]],*,min_forward_n:int=40,min_forward_days:int=14,margin:float=.01)->dict[str,Any]:
    rows=[]
    for m in models:
        x=dict(m);x['eligible']=_eligible(x,min_forward_n,min_forward_days);rows.append(x)
    eligible=[x for x in rows if x['eligible']]
    eligible.sort(key=lambda x:float(x['mean_excess_return']),reverse=True)
    champion=eligible[0] if eligible else None
    challenger=eligible[1] if len(eligible)>1 else None
    replace=False
    if champion and challenger:
        replace=float(challenger['mean_excess_return'])>float(champion['mean_excess_return'])+margin
    blockers=[]
    if not champion:
        blockers=['MIN_MATURE_FORWARD_SAMPLE_OR_DAYS_NOT_MET','FORWARD_COST_BENCHMARK_EVIDENCE_REQUIRED']
    return {'status':'READY' if champion else 'INSUFFICIENT_EVIDENCE','champion':champion,'challenger':challenger,
            'replacement_recommended':replace,'automatic_replacement':False,'weights_applied_automatically':False,
            'promotion_scope':'SHADOW_PAPER_ONLY','blockers':blockers,'min_forward_n':min_forward_n,
            'min_forward_days':min_forward_days,'can_trade':False,'real_trading':False}
