"""Model degradation + competition v3 for forward-only evidence."""
from __future__ import annotations

REAL_TRADING=False


def _f(x):
    try:return float(x)
    except (TypeError,ValueError):return None


def assess_model(model,policy=None):
    p={'min_samples':30,'max_brier':0.25,'min_hit_rate':0.50,'min_excess_pct':-1.0}
    p.update(policy or {})
    m=model or {}; n=int(m.get('samples') or 0); b=_f(m.get('brier')); hit=_f(m.get('hit_rate')); excess=_f(m.get('excess_return_pct'))
    if n<int(p['min_samples']) or None in (b,hit,excess):
        return {'status':'INSUFFICIENT_EVIDENCE','eligible':False,'score':None,'recommended_weight':0.0,'real_trading':False}
    degraded=b>p['max_brier'] or hit<p['min_hit_rate'] or excess<p['min_excess_pct']
    score=(1.0-b)+hit+max(-1.0,min(1.0,excess/10.0))
    return {'status':'DEGRADED' if degraded else 'STABLE','eligible':not degraded,'score':score,'recommended_weight':0.0,'real_trading':False}


def compete_models(models,policy=None):
    rows=[]
    for m in models or []:
        a=assess_model(m,policy); row={'model_id':m.get('model_id'),**a}; rows.append(row)
    eligible=[r for r in rows if r.get('eligible') and r.get('score') is not None]
    total=sum(max(0.0,float(r['score'])) for r in eligible)
    for r in rows:
        if r in eligible:r['recommended_weight']=(max(0.0,float(r['score']))/total if total>0 else 0.0)
    return {'models':rows,'winner':(max(eligible,key=lambda r:r['recommended_weight']).get('model_id') if eligible else None),'automatic_application':False,'policy_note':'Weights are governance recommendations, not auto-applied and not validated as optimal.','real_trading':False}
