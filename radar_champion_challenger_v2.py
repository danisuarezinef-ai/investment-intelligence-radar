"""Forward-only champion/challenger governance v2.

A challenger may outrank the current champion, but replacement is recommendation-only
inside SHADOW/PAPER. Historical or simulated evidence cannot promote a model.
"""
from __future__ import annotations
from typing import Any,Iterable
from radar_champion_challenger_v1 import derive_forward_model_metrics
REAL_TRADING=False


def _eligible(m,min_forward_n,min_forward_days):
    return int(m.get('forward_n') or 0)>=int(min_forward_n) and int(m.get('forward_days') or 0)>=int(min_forward_days) and m.get('forward_only') is True and m.get('matured_only') is True and m.get('backfilled') is not True and m.get('cost_aware') is True and m.get('benchmark_aware') is True and isinstance(m.get('mean_excess_return'),(int,float))


def compete_v2(models:Iterable[dict[str,Any]],*,current_champion_version=None,min_forward_n=40,min_forward_days=14,margin=.01):
    rows=[]
    for raw in models or []:
        x=dict(raw);x['eligible']=_eligible(x,min_forward_n,min_forward_days);rows.append(x)
    eligible=[x for x in rows if x['eligible']]
    eligible.sort(key=lambda x:float(x['mean_excess_return']),reverse=True)
    current=None
    if current_champion_version:
        current=next((x for x in eligible if x.get('model_version')==current_champion_version),None)
    if current is None and eligible:current=eligible[0]
    challengers=[x for x in eligible if not current or x.get('model_version')!=current.get('model_version')]
    best=challengers[0] if challengers else None
    replacement=bool(current and best and float(best['mean_excess_return'])>float(current['mean_excess_return'])+float(margin))
    blockers=[]
    if not current:blockers.append('NO_MATURE_FORWARD_CHAMPION')
    if not best:blockers.append('NO_MATURE_FORWARD_CHALLENGER')
    return {'status':'READY' if current else 'INSUFFICIENT_EVIDENCE','current_champion':current,'best_challenger':best,
            'replacement_recommended':replacement,'replacement_margin':float(margin),
            'automatic_replacement':False,'promotion_scope':'SHADOW_PAPER_ONLY','blockers':blockers,
            'candidate_count':len(eligible),'can_trade':False,'real_trading':False}


def compete_records(records,**kwargs):return compete_v2(derive_forward_model_metrics(records),**kwargs)
