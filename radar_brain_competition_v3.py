"""Forward-only Champion/Challenger, ensemble and meta-learning analytics.

Competition is advisory and SHADOW/PAPER-only.  Historical evidence can describe a
candidate but cannot promote it.  Dynamic routing is evaluated sequentially using only
records whose outcomes were already known before each routed decision.
"""
from __future__ import annotations

import math
from collections import defaultdict
from datetime import datetime, timezone
from statistics import mean, pstdev

REAL_TRADING = False
MIN_FORWARD_N = 40
MIN_FORWARD_DAYS = 14


def _dt(v):
    try:
        d=datetime.fromisoformat(str(v).replace('Z','+00:00'))
        if d.tzinfo is None:d=d.replace(tzinfo=timezone.utc)
        return d.astimezone(timezone.utc)
    except Exception:return None


def _f(v):
    try:
        x=float(v);return x if math.isfinite(x) else None
    except Exception:return None


def comparable_forward_rows(rows):
    out=[]
    for r in rows or []:
        if r.get('matured') is not True or r.get('natural') is not True:continue
        ex=_f(r.get('excess_return'));ev=_dt(r.get('evaluated_at'));created=_dt(r.get('created_at'))
        if ex is None or not ev or not created:continue
        x=dict(r);x['excess_return']=ex;x['_evaluated_dt']=ev;x['_created_dt']=created
        x['comparison_cell']='|'.join((str(r.get('horizon') or 'UNKNOWN'),str(r.get('regime') or 'UNKNOWN')))
        out.append(x)
    return out


def model_forward_metrics(rows):
    groups=defaultdict(list)
    for r in comparable_forward_rows(rows):groups[str(r.get('model_version') or '')].append(r)
    result=[]
    for model,xs in groups.items():
        if not model:continue
        dates=sorted(r['_created_dt'] for r in xs)
        days=(dates[-1].date()-dates[0].date()).days+1 if dates else 0
        excess=[r['excess_return'] for r in xs]
        cells=defaultdict(list)
        for r in xs:cells[r['comparison_cell']].append(r['excess_return'])
        result.append({'model_version':model,'forward_n':len(xs),'forward_days':days,
                       'mean_excess_return':mean(excess),'stdev_excess_return':pstdev(excess) if len(excess)>1 else 0.0,
                       'cells':{k:{'n':len(v),'mean_excess':mean(v)} for k,v in cells.items()},
                       'eligible':len(xs)>=MIN_FORWARD_N and days>=MIN_FORWARD_DAYS,
                       'forward_only':True,'backfilled':False,'matured_only':True,
                       'automatic_promotion':False,'real_trading':False})
    return sorted(result,key=lambda x:x['mean_excess_return'],reverse=True)


def champion_challenger_v3(rows, min_n=MIN_FORWARD_N, min_days=MIN_FORWARD_DAYS, margin=.001):
    metrics=model_forward_metrics(rows)
    for m in metrics:m['eligible']=m['forward_n']>=min_n and m['forward_days']>=min_days
    eligible=[m for m in metrics if m['eligible']]
    champion=eligible[0] if eligible else None
    challenger=eligible[1] if len(eligible)>1 else None
    recommend=False
    if champion and challenger:
        # Both candidates must share at least one forward comparison cell.  A global
        # average across disjoint regimes/horizons is not comparable evidence.
        shared=set(champion['cells']) & set(challenger['cells'])
        if shared:
            recommend=challenger['mean_excess_return']>champion['mean_excess_return']+margin
    else:shared=set()
    return {'status':'READY_FOR_MANUAL_COMPARISON' if champion and challenger and shared else 'PENDING_SAMPLE',
            'models':metrics,'champion':champion,'challenger':challenger,'shared_cells':sorted(shared),
            'replacement_recommended':recommend,'automatic_replacement':False,
            'promotion_scope':'SHADOW_PAPER_ONLY','min_forward_n':min_n,'min_forward_days':min_days,
            'can_trade':False,'real_trading':False}


def champion_degradation_v2(rows, model_version=None, min_segment=20):
    xs=[r for r in comparable_forward_rows(rows) if model_version in (None,r.get('model_version'))]
    xs=sorted(xs,key=lambda r:r['_created_dt'])
    if len(xs)<2*min_segment:
        return {'status':'PENDING_SAMPLE','n':len(xs),'degradation_verified':False,'real_trading':False}
    older=xs[:len(xs)//2];recent=xs[len(xs)//2:]
    a=mean(r['excess_return'] for r in older);b=mean(r['excess_return'] for r in recent)
    sd=pstdev([r['excess_return'] for r in xs]) if len(xs)>1 else 0
    threshold=max(.001,.5*sd/math.sqrt(max(1,len(recent))))
    degraded=b<a-threshold
    return {'status':'PASS','n':len(xs),'older_mean_excess':a,'recent_mean_excess':b,
            'degradation_verified':degraded,'threshold':threshold,
            'automatic_demotion':False,'real_trading':False}


def _corr(a,b):
    if len(a)!=len(b) or len(a)<3:return None
    ma=mean(a);mb=mean(b);sa=sum((x-ma)**2 for x in a);sb=sum((y-mb)**2 for y in b)
    if sa<=0 or sb<=0:return None
    return sum((x-ma)*(y-mb) for x,y in zip(a,b))/math.sqrt(sa*sb)


def model_correlations(rows):
    xs=comparable_forward_rows(rows)
    # Align model outcomes by a contemporaneous observable key rather than prediction id.
    aligned=defaultdict(dict)
    for r in xs:
        created=r['_created_dt'].replace(minute=0,second=0,microsecond=0).isoformat()
        key=(created,r.get('symbol'),r.get('horizon'))
        aligned[key][str(r.get('model_version'))]=r['excess_return']
    models=sorted({m for cell in aligned.values() for m in cell})
    pairs={}
    for i,a in enumerate(models):
        for b in models[i+1:]:
            va=[];vb=[]
            for cell in aligned.values():
                if a in cell and b in cell:va.append(cell[a]);vb.append(cell[b])
            pairs[f'{a}|{b}']={'n':len(va),'correlation':_corr(va,vb)}
    return {'models':models,'pairs':pairs,'real_trading':False}


def shadow_ensemble_v2(rows, correlation_ceiling=.90):
    competition=champion_challenger_v3(rows);corr=model_correlations(rows)
    eligible=[m for m in competition['models'] if m.get('eligible')]
    selected=[]
    for m in eligible:
        name=m['model_version'];too_correlated=False
        for prior in selected:
            key='|'.join(sorted((name,prior)))
            c=(corr['pairs'].get(key) or {}).get('correlation')
            if c is not None and abs(c)>=correlation_ceiling:too_correlated=True;break
        if not too_correlated:selected.append(name)
    status='PASS' if len(selected)>=2 else 'PENDING_SAMPLE'
    return {'status':status,'selected_models':selected,'correlations':corr,
            'correlation_ceiling':correlation_ceiling,'correlation_penalty_active':True,
            'weights_applied_automatically':False,'scope':'SHADOW_ONLY','real_trading':False}


def diversity_reward_evidence(rows):
    ensemble=shadow_ensemble_v2(rows)
    if len(ensemble['selected_models'])<2:
        return {'status':'PENDING_SAMPLE','incremental_forward_value':None,'real_trading':False}
    # Require matched cells across selected models; otherwise diversity is cosmetic.
    xs=comparable_forward_rows(rows);selected=set(ensemble['selected_models']);cells=defaultdict(dict)
    for r in xs:
        key=(r['_created_dt'].replace(minute=0,second=0,microsecond=0).isoformat(),r.get('symbol'),r.get('horizon'))
        if r.get('model_version') in selected:cells[key][r.get('model_version')]=r['excess_return']
    matched=[v for v in cells.values() if selected.issubset(v)]
    if len(matched)<20:return {'status':'PENDING_SAMPLE','matched_n':len(matched),'incremental_forward_value':None,'real_trading':False}
    ensemble_returns=[mean([cell[m] for m in selected]) for cell in matched]
    individual={m:mean([cell[m] for cell in matched]) for m in selected}
    incremental=mean(ensemble_returns)-max(individual.values())
    return {'status':'PASS' if incremental>0 else 'FAILED','matched_n':len(matched),
            'ensemble_mean_excess':mean(ensemble_returns),'individual_mean_excess':individual,
            'incremental_forward_value':incremental,'real_trading':False}


def sequential_dynamic_routing(rows, min_history=20):
    """Evaluate routing with strict outcome-known-before-decision chronology."""
    xs=comparable_forward_rows(rows);xs=sorted(xs,key=lambda r:r['_created_dt'])
    history=[];routed=[];violations=[]
    for current in xs:
        cutoff=current['_created_dt']
        available=[r for r in history if r['_evaluated_dt']<=cutoff]
        cell=current['comparison_cell']
        by=defaultdict(list)
        for r in available:
            if r['comparison_cell']==cell:by[str(r.get('model_version'))].append(r['excess_return'])
        eligible={m:mean(v) for m,v in by.items() if len(v)>=min_history}
        if eligible:
            chosen=max(eligible,key=eligible.get)
            if str(current.get('model_version'))==chosen:
                routed.append(current['excess_return'])
        # Explicit audit invariant: no row with evaluated_at after the decision cutoff
        # may enter the routing history.
        if any(r['_evaluated_dt']>cutoff for r in available):violations.append(current.get('prediction_id'))
        history.append(current)
    return {'status':'PASS' if routed and not violations else ('FAILED' if violations else 'PENDING_SAMPLE'),
            'routed_n':len(routed),'mean_excess':mean(routed) if routed else None,
            'lookahead_violations':violations,'uses_future_outcomes':False,
            'min_history_per_cell_model':min_history,'real_trading':False}


def meta_learning_audit(rows):
    routing=sequential_dynamic_routing(rows)
    xs=comparable_forward_rows(rows)
    baseline=[r['excess_return'] for r in xs]
    if routing['status']!='PASS' or routing['routed_n']<20 or not baseline:
        return {'status':'PENDING_SAMPLE','routing':routing,'incremental_excess':None,'real_trading':False}
    incremental=float(routing['mean_excess'])-mean(baseline)
    return {'status':'PASS' if incremental>0 else 'FAILED','routing':routing,
            'baseline_mean_excess':mean(baseline),'incremental_excess':incremental,
            'method_selection_improved_forward':incremental>0,'real_trading':False}


def historical_live_transfer_v2(rows, historical_metrics=None):
    hist=historical_metrics or {};forward=model_forward_metrics(rows)
    pairs=[]
    for f in forward:
        h=hist.get(f['model_version']) if isinstance(hist,dict) else None
        if not isinstance(h,dict):continue
        hv=_f(h.get('score',h.get('mean_gain')));fv=_f(f.get('mean_excess_return'))
        if hv is None or fv is None:continue
        pairs.append((hv,fv,f['model_version']))
    if len(pairs)<2:
        return {'status':'PENDING_SAMPLE','matched_models':len(pairs),'transfer_score':None,
                'historical_cannot_promote':True,'real_trading':False}
    hs=[x[0] for x in pairs];fs=[x[1] for x in pairs];c=_corr(hs,fs)
    return {'status':'PASS' if c is not None else 'PENDING_SAMPLE','matched_models':len(pairs),
            'transfer_score':c,'pairs':[{'model_version':m,'historical':h,'forward':f} for h,f,m in pairs],
            'historical_cannot_promote':True,'real_trading':False}


def competition_snapshot(rows, historical_metrics=None):
    cc=champion_challenger_v3(rows);deg=champion_degradation_v2(rows,cc.get('champion',{}).get('model_version') if cc.get('champion') else None)
    ensemble=shadow_ensemble_v2(rows);div=diversity_reward_evidence(rows);routing=sequential_dynamic_routing(rows)
    meta=meta_learning_audit(rows);transfer=historical_live_transfer_v2(rows,historical_metrics)
    return {'status':'BRAIN_COMPETITION_V3','champion_challenger':cc,'champion_degradation':deg,
            'shadow_ensemble':ensemble,'diversity_reward':div,'dynamic_routing':routing,
            'meta_learning':meta,'historical_live_transfer':transfer,
            'automatic_promotion':False,'automatic_demotion':False,'automatic_replacement':False,
            'can_trade':False,'real_trading':False}
