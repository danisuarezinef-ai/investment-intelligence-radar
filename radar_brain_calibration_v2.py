"""Forward-only calibration, uncertainty, abstention and alpha analytics.

All metrics consume canonical prospective evidence.  They are descriptive/advisory;
none can place orders or promote a model.  Heuristic decompositions are labelled as
such and cannot satisfy empirical maturity gates on their own.
"""
from __future__ import annotations

import hashlib
import json
import math
from collections import Counter, defaultdict
from statistics import mean, pstdev

REAL_TRADING = False


def _finite(value):
    try:
        x=float(value)
        return x if math.isfinite(x) else None
    except Exception:
        return None


def _action_rows(rows):
    return [r for r in (rows or []) if r.get('matured') is True and r.get('natural') is True
            and str(r.get('decision_state') or '').upper() in {'BUY','SELL'} and r.get('action_hit') is not None]


def calibration_engine_v2(rows, bins=10):
    valid=[]
    for r in _action_rows(rows):
        p=_finite(r.get('confidence'))
        if p is None or not 0 <= p <= 1:
            continue
        valid.append((p,1.0 if r.get('action_hit') else 0.0,r))
    if not valid:
        return {'status':'PENDING_SAMPLE','n':0,'brier':None,'log_loss':None,'ece':None,
                'reliability':[],'real_trading':False}
    brier=mean((p-y)**2 for p,y,_ in valid)
    eps=1e-12
    logloss=-mean(y*math.log(max(eps,min(1-eps,p)))+(1-y)*math.log(max(eps,min(1-eps,1-p))) for p,y,_ in valid)
    buckets=defaultdict(list)
    for p,y,r in valid:
        buckets[min(bins-1,int(p*bins))].append((p,y,r))
    reliability=[];ece=0.0
    for b,vals in sorted(buckets.items()):
        predicted=mean(x[0] for x in vals);observed=mean(x[1] for x in vals);w=len(vals)/len(valid)
        ece += w*abs(predicted-observed)
        reliability.append({'bin':b,'n':len(vals),'predicted':predicted,'observed':observed,
                            'abs_error':abs(predicted-observed)})
    return {'status':'PASS' if len(valid)>=50 else 'PENDING_SAMPLE','n':len(valid),'brier':brier,
            'log_loss':logloss,'ece':ece,'reliability':reliability,'bins':bins,
            'forward_only':True,'can_trade':False,'real_trading':False}


def calibration_drift(rows, min_half=20):
    xs=_action_rows(rows)
    xs=sorted(xs,key=lambda r:str(r.get('created_at') or ''))
    if len(xs)<2*int(min_half):
        return {'status':'PENDING_SAMPLE','n':len(xs),'older':None,'newer':None,'delta_ece':None,
                'real_trading':False}
    cut=len(xs)//2
    older=calibration_engine_v2(xs[:cut]);newer=calibration_engine_v2(xs[cut:])
    if older.get('ece') is None or newer.get('ece') is None:
        status='PENDING_SAMPLE';delta=None
    else:
        delta=newer['ece']-older['ece'];status='DEGRADED' if delta>.10 else 'PASS'
    return {'status':status,'n':len(xs),'older':{'n':older['n'],'ece':older['ece'],'brier':older['brier']},
            'newer':{'n':newer['n'],'ece':newer['ece'],'brier':newer['brier']},'delta_ece':delta,
            'threshold':.10,'real_trading':False}


def confidence_decomposition(row):
    payload=row.get('payload') or {};features=payload.get('features') or {};provenance=row.get('provenance') or {}
    raw=max(0.0,min(1.0,float(row.get('confidence') or 0)))
    quality=max(0.0,min(1.0,float(row.get('quality') or 0)))
    source=_finite(features.get('source_quality'))
    source=max(0.0,min(1.0,source)) if source is not None else None
    regime_known=row.get('regime') not in (None,'','UNKNOWN')
    model=max(0.0,min(1.0,2*abs(raw-.5)))
    components={
        'reported_confidence':raw,
        'model_strength':model,
        'data_quality':quality,
        'source_quality':source,
        'regime_context':1.0 if regime_known else None,
        'lookahead_safe':1.0 if provenance.get('lookahead') is False else 0.0,
        'consensus':None,
    }
    known=[x for k,x in components.items() if k not in {'reported_confidence'} and isinstance(x,(int,float))]
    support=mean(known) if known else 0.0
    ceiling=min(.90,.50+.40*support)
    if source is None:ceiling=min(ceiling,.75)
    if not regime_known:ceiling=min(ceiling,.70)
    adjusted=min(raw,ceiling)
    return {'components':components,'support':support,'confidence_ceiling':ceiling,
            'adjusted_confidence':adjusted,'method':'HEURISTIC_FAIL_CLOSED_DECOMPOSITION',
            'empirically_calibrated_decomposition':False,'real_trading':False}


def uncertainty_decomposition(row):
    payload=row.get('payload') or {};features=payload.get('features') or {}
    quality=max(0.0,min(1.0,float(row.get('quality') or 0)))
    volatility=_finite(features.get('volatility'))
    # These are bounded diagnostic proxies, not claims of identifiable statistical variance.
    epistemic=max(0.0,min(1.0,1.0-quality))
    if row.get('regime') in (None,'','UNKNOWN'):epistemic=min(1.0,epistemic+.15)
    aleatoric=None if volatility is None else max(0.0,min(1.0,volatility/(1.0+volatility)))
    return {'epistemic_proxy':epistemic,'aleatoric_proxy':aleatoric,
            'identification':'HEURISTIC_PROXIES_NOT_VARIANCE_DECOMPOSITION','real_trading':False}


def abstention_decision_v3(row, *, min_adjusted_confidence=.60, min_quality=.80):
    c=confidence_decomposition(row);u=uncertainty_decomposition(row)
    reasons=[]
    if c['adjusted_confidence']<min_adjusted_confidence:reasons.append('LOW_ADJUSTED_CONFIDENCE')
    if float(row.get('quality') or 0)<min_quality:reasons.append('INSUFFICIENT_EVIDENCE_QUALITY')
    if u.get('epistemic_proxy') is not None and u['epistemic_proxy']>.35:reasons.append('HIGH_EPISTEMIC_UNCERTAINTY')
    if row.get('regime') in (None,'','UNKNOWN'):reasons.append('REGIME_UNKNOWN')
    abstain=bool(reasons)
    return {'decision':'NO_INVERTIR / ESPERAR' if abstain else 'EVALUABLE_PAPER_SIGNAL',
            'abstain':abstain,'reasons':reasons,'adjusted_confidence':c['adjusted_confidence'],
            'confidence_ceiling':c['confidence_ceiling'],'epistemic_proxy':u['epistemic_proxy'],
            'minimum_adjusted_confidence':min_adjusted_confidence,'minimum_quality':min_quality,
            'paper_only':True,'can_trade':False,'real_trading':False}


def abstention_quality(rows, min_n=30):
    observations=[]
    for r in _action_rows(rows):
        a=abstention_decision_v3(r)
        ex=_finite(r.get('excess_return'))
        if ex is None:continue
        observations.append((a['abstain'],ex))
    abst=[x for flag,x in observations if flag];act=[x for flag,x in observations if not flag]
    if len(observations)<min_n or not abst or not act:
        status='PENDING_SAMPLE'
    else:
        # Useful abstention means the skipped set is worse than the retained set.
        status='PASS' if mean(abst)<mean(act) else 'FAILED'
    return {'status':status,'n':len(observations),'abstained_n':len(abst),'retained_n':len(act),
            'abstained_mean_excess':mean(abst) if abst else None,
            'retained_mean_excess':mean(act) if act else None,
            'avoided_negative_rate':sum(1 for x in abst if x<0)/len(abst) if abst else None,
            'real_trading':False}


def _interval(values,z=1.96):
    xs=[x for x in (_finite(v) for v in values or []) if x is not None]
    if len(xs)<2:return {'n':len(xs),'mean':xs[0] if xs else None,'low':None,'high':None}
    m=mean(xs);sd=pstdev(xs);se=sd/math.sqrt(len(xs));return {'n':len(xs),'mean':m,'low':m-z*se,'high':m+z*se}


def downside_distribution(values):
    xs=sorted(x for x in (_finite(v) for v in values or []) if x is not None)
    if not xs:return {'n':0,'loss_probability':None,'p05':None,'p01':None,'expected_shortfall_05':None}
    def quantile(p):
        idx=max(0,min(len(xs)-1,int(math.floor(p*(len(xs)-1)))))
        return xs[idx]
    k=max(1,int(math.ceil(.05*len(xs))))
    return {'n':len(xs),'loss_probability':sum(1 for x in xs if x<0)/len(xs),
            'p05':quantile(.05),'p01':quantile(.01),'expected_shortfall_05':mean(xs[:k])}


def alpha_summary(rows):
    actions=[r for r in _action_rows(rows) if _finite(r.get('excess_return')) is not None]
    excess=[float(r['excess_return']) for r in actions]
    net=[_finite(r.get('net_return')) for r in actions];net=[x for x in net if x is not None]
    raw=[_finite(r.get('raw_return')) for r in actions];raw=[x for x in raw if x is not None]
    costs=[_finite(r.get('cost')) for r in actions];costs=[x for x in costs if x is not None]
    return {'status':'PASS' if len(actions)>=30 else 'PENDING_SAMPLE','n':len(actions),
            'mean_excess_return':mean(excess) if excess else None,
            'mean_net_return':mean(net) if net else None,'mean_raw_asset_return':mean(raw) if raw else None,
            'mean_cost':mean(costs) if costs else None,'interval_excess':_interval(excess),
            'downside_excess':downside_distribution(excess),'cost_complete':len(costs)==len(actions) and bool(actions),
            'benchmark_complete':len(excess)==len(actions) and bool(actions),'real_trading':False}


def signal_decay_by_family(rows):
    # With independent horizons, decay can only be estimated when the same family has
    # mature outcomes at >=2 horizons.  Do not infer 1w/1m/3m from 1d.
    by=defaultdict(lambda:defaultdict(list))
    for r in _action_rows(rows):
        ex=_finite(r.get('excess_return'))
        if ex is None:continue
        by[str(r.get('family') or 'UNKNOWN')][str(r.get('horizon') or '')].append(ex)
    result={}
    for family,horizons in by.items():
        means={h:mean(v) for h,v in horizons.items() if v}
        ordered=[h for h in ('1d','1w','1m','3m') if h in means]
        status='PASS' if len(ordered)>=2 else 'PENDING_SAMPLE'
        half_life=None
        if len(ordered)>=2:
            initial=abs(means[ordered[0]])
            for h in ordered[1:]:
                if abs(means[h])<=initial/2:
                    half_life=h;break
        result[family]={'status':status,'means':means,'half_life_horizon':half_life,'mature_horizons':ordered}
    return {'status':'PASS' if result and any(x['status']=='PASS' for x in result.values()) else 'PENDING_SAMPLE',
            'families':result,'real_trading':False}


def failure_attribution(rows):
    counts=Counter();examples=[]
    for r in _action_rows(rows):
        ex=_finite(r.get('excess_return'))
        if ex is None or ex>=0:continue
        q=r.get('quality_checks') or {};payload=r.get('payload') or {};out=r.get('outcome') or {}
        if not q.get('pit_valid') or not q.get('natural'):reason='DATA_OR_PROVENANCE'
        elif out.get('cost') is not None and _finite(out.get('net_return')) is not None and _finite(out.get('return')) is not None and float(out.get('return'))>0>=float(out.get('net_return')):reason='COST_DRAG'
        elif r.get('regime') in (None,'','UNKNOWN'):reason='REGIME_UNCERTAINTY'
        elif str(r.get('decision_state')).upper() in {'BUY','SELL'} and r.get('action_hit') is False:reason='DIRECTION_OR_TIMING'
        else:reason='BENCHMARK_UNDERPERFORMANCE'
        counts[reason]+=1
        if len(examples)<20:examples.append({'prediction_id':r.get('prediction_id'),'symbol':r.get('symbol'),'reason':reason,'excess_return':ex})
    n=sum(counts.values())
    return {'status':'PASS' if n>=20 else 'PENDING_SAMPLE','n_failures':n,'categories':dict(counts),
            'examples':examples,'causal_claim':False,'taxonomy':'DIAGNOSTIC_NOT_CAUSAL','real_trading':False}


def observational_alpha_attribution(rows):
    actions=[r for r in _action_rows(rows) if _finite(r.get('excess_return')) is not None]
    grouped={}
    for key in ('family','regime','horizon'):
        cells=defaultdict(list)
        for r in actions:cells[str(r.get(key) or 'UNKNOWN')].append(float(r['excess_return']))
        grouped[key]={k:{'n':len(v),'mean_excess':mean(v)} for k,v in cells.items()}
    return {'status':'PENDING_SAMPLE' if not actions else 'AVAILABLE_DIAGNOSTIC',
            'groups':grouped,'causal_attribution_verified':False,
            'note':'group means are observational and cannot prove source-level causal alpha',
            'real_trading':False}


def rank_369(rows, limit=9):
    # Use the newest open prediction per symbol/horizon. Scores are risk/evidence adjusted
    # and remain PAPER advisory only.
    latest={}
    for r in rows or []:
        if r.get('matured') is True:continue
        key=(r.get('symbol'),r.get('horizon'))
        if key not in latest or str(r.get('created_at') or '')>str(latest[key].get('created_at') or ''):latest[key]=r
    candidates=[]
    for r in latest.values():
        payload=r.get('payload') or {};score=_finite(payload.get('score')) or 0.0
        c=confidence_decomposition(r);u=uncertainty_decomposition(r);a=abstention_decision_v3(r)
        risk=(u.get('aleatoric_proxy') if u.get('aleatoric_proxy') is not None else .5)
        adjusted=score*c['adjusted_confidence']*(float(r.get('quality') or 0))-abs(score)*.25*risk
        candidates.append({'symbol':r.get('symbol'),'horizon':r.get('horizon'),'model_version':r.get('model_version'),
                           'raw_score':score,'quality':r.get('quality'),'adjusted_confidence':c['adjusted_confidence'],
                           'risk_proxy':risk,'ranking_score':adjusted,'abstention':a['decision'],
                           'can_trade':False,'real_trading':False})
    candidates.sort(key=lambda x:x['ranking_score'],reverse=True)
    top=candidates[:max(0,int(limit))]
    return {'status':'AVAILABLE' if top else 'PENDING_SAMPLE','top3':top[:3],'top6':top[:6],'top9':top[:9],
            'uses_uncertainty':True,'uses_evidence_quality':True,'uses_downside_proxy':True,
            'can_trade':False,'real_trading':False}


def brain_analytics_snapshot(rows):
    cal=calibration_engine_v2(rows);drift=calibration_drift(rows);abst=abstention_quality(rows)
    alpha=alpha_summary(rows);decay=signal_decay_by_family(rows);failures=failure_attribution(rows)
    attrib=observational_alpha_attribution(rows);ranking=rank_369(rows)
    payload={'calibration':cal,'drift':drift,'abstention_quality':abst,'alpha':alpha,
             'decay':decay,'failure_attribution':failures,'alpha_attribution':attrib,'ranking_369':ranking}
    raw=json.dumps(payload,sort_keys=True,separators=(',',':'),default=str).encode()
    payload['snapshot_hash']=hashlib.sha256(raw).hexdigest()
    payload.update({'status':'BRAIN_ANALYTICS_V2','can_trade':False,'real_trading':False})
    return payload
