"""Forward-only champion/challenger governance."""
from __future__ import annotations
from typing import Any, Iterable
REAL_TRADING=False

def compete(models: Iterable[dict[str,Any]], *, min_forward_n:int=40, margin:float=.01) -> dict[str,Any]:
    rows=[]
    for m in models:
        x=dict(m); n=int(x.get('forward_n') or 0)
        eligible=n>=min_forward_n and x.get('backfilled') is not True and isinstance(x.get('mean_excess_return'),(int,float))
        x['eligible']=eligible; rows.append(x)
    eligible=[x for x in rows if x['eligible']]
    eligible.sort(key=lambda x:float(x['mean_excess_return']),reverse=True)
    champion=eligible[0] if eligible else None
    challenger=eligible[1] if len(eligible)>1 else None
    replace=False
    if champion and challenger:
        replace=float(challenger['mean_excess_return']) > float(champion['mean_excess_return'])+margin
    return {'status':'READY' if champion else 'INSUFFICIENT_EVIDENCE','champion':champion,'challenger':challenger,
            'replacement_recommended':replace,'automatic_replacement':False,'weights_applied_automatically':False,
            'can_trade':False,'real_trading':False}
