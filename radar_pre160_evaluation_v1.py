"""Pre-1.6 evaluation primitives shared by League, reports and mobile surfaces.

All functions are deterministic/read-only. Missing evidence remains explicit; no
missing value is silently converted into a performance success. REAL_TRADING is off.
"""
from __future__ import annotations

from collections import defaultdict
import math
import statistics

REAL_TRADING=False


def clamp(x,lo=0.0,hi=100.0):
    try:return max(lo,min(hi,float(x)))
    except (TypeError,ValueError):return lo


def _f(x,default=None):
    try:
        v=float(x);return v if math.isfinite(v) else default
    except (TypeError,ValueError):return default


def _hit(x):
    if x is True or x==1:return 1.0
    if x is False or x==0:return 0.0
    s=str(x).lower()
    if s in ('hit','win','positive','true'):return 1.0
    if s in ('miss','loss','negative','false'):return 0.0
    return None


def confidence_interval(values,z=1.96):
    vals=[float(x) for x in values or [] if _f(x) is not None]
    if len(vals)<2:return {'n':len(vals),'mean':statistics.mean(vals) if vals else None,'low':None,'high':None,'method':'INSUFFICIENT_EVIDENCE'}
    mean=statistics.mean(vals);sd=statistics.stdev(vals);half=float(z)*sd/math.sqrt(len(vals))
    return {'n':len(vals),'mean':mean,'low':mean-half,'high':mean+half,'method':'NORMAL_APPROXIMATION'}


def horizon_quality(records,horizons=('1d','1w','1m','3m')):
    groups={h:[] for h in horizons};hits={h:[] for h in horizons}
    for r in records or []:
        if r.get('backfilled') is True:continue
        if r.get('immutable') is False:continue
        h=str(r.get('horizon') or '')
        if h not in groups:continue
        outcome=r.get('outcome') if isinstance(r.get('outcome'),dict) else r
        ret=_f(outcome.get('net_return_pct',outcome.get('return_pct')))
        if ret is not None:groups[h].append(ret)
        hit=_hit(outcome.get('hit')); 
        if hit is not None:hits[h].append(hit)
    out={}
    for h in horizons:
        vals=groups[h];hr=statistics.mean(hits[h]) if hits[h] else None
        out[h]={'n':len(vals),'mean_return_pct':statistics.mean(vals) if vals else None,
                'hit_rate':hr,'return_ci95':confidence_interval(vals),
                'status':'AVAILABLE' if vals else 'INSUFFICIENT_EVIDENCE'}
    return {'horizons':out,'real_trading':False}


def regime_generalization(records,min_per_regime=3):
    groups=defaultdict(list)
    for r in records or []:
        regime=str(r.get('regime') or 'UNKNOWN').upper();ret=_f(r.get('net_return_pct',r.get('return_pct')))
        if regime!='UNKNOWN' and ret is not None:groups[regime].append(ret)
    eligible={k:v for k,v in groups.items() if len(v)>=int(min_per_regime)}
    if len(eligible)<2:
        return {'regimes_evaluated':len(eligible),'generalization_score':None,'status':'INSUFFICIENT_REGIME_EVIDENCE','by_regime':{},'real_trading':False}
    means={k:statistics.mean(v) for k,v in eligible.items()};mean_all=statistics.mean(means.values());disp=statistics.pstdev(means.values()) if len(means)>1 else 0
    profitable=sum(1 for x in means.values() if x>0)/len(means)
    breadth=min(1.0,len(means)/5.0);disp_penalty=min(50.0,disp*5.0)
    score=clamp(45+30*profitable+20*breadth-disp_penalty+5*math.tanh(mean_all/3.0))
    return {'regimes_evaluated':len(eligible),'generalization_score':score,'status':'OBSERVED_REGIME_LINKAGE',
            'by_regime':{k:{'n':len(eligible[k]),'mean_return_pct':means[k]} for k in sorted(eligible)},'dispersion_pct':disp,'real_trading':False}


def historical_live_transfer(historical,live):
    """Score 0..100 for whether historical quality transfers to prospective PAPER/forward."""
    h=historical or {};l=live or {};components={};weights={'hit_rate':.25,'excess_return_pct':.30,'max_drawdown_pct':.20,'decision_quality':.25}
    scales={'hit_rate':.25,'excess_return_pct':8.0,'max_drawdown_pct':10.0,'decision_quality':25.0}
    for key,w in weights.items():
        a=_f(h.get(key));b=_f(l.get(key))
        if a is None or b is None:continue
        diff=abs(a-b);components[key]=clamp(100-diff/scales[key]*100)
    if not components:return {'score':None,'status':'INSUFFICIENT_EVIDENCE','components':{},'real_trading':False}
    used=sum(weights[k] for k in components);score=sum(components[k]*weights[k] for k in components)/used
    return {'score':score,'status':'AVAILABLE','components':components,'real_trading':False}


def anti_overfitting_score(train,walk_forward,vault=None,final_test=None):
    """Penalize collapse from train to increasingly protected evidence layers."""
    layers=[('walk_forward',walk_forward,.35),('vault',vault,.30),('final_test',final_test,.35)]
    t=train or {};scores=[];details={}
    for name,obj,w in layers:
        if not obj:continue
        parts=[]
        for key,scale in (('hit_rate',.25),('excess_return_pct',8.0),('decision_quality',25.0)):
            a=_f(t.get(key));b=_f(obj.get(key))
            if a is not None and b is not None:parts.append(clamp(100-abs(a-b)/scale*100))
        if parts:
            s=statistics.mean(parts);scores.append((s,w));details[name]=s
    if not scores:return {'score':None,'status':'INSUFFICIENT_EVIDENCE','layers':details,'real_trading':False}
    den=sum(w for _,w in scores);score=sum(s*w for s,w in scores)/den
    return {'score':score,'status':'AVAILABLE','layers':details,'real_trading':False}


def _corr(a,b):
    n=min(len(a),len(b))
    if n<3:return None
    x=list(map(float,a[-n:]));y=list(map(float,b[-n:]));sx=statistics.pstdev(x);sy=statistics.pstdev(y)
    if sx<=1e-12 or sy<=1e-12:return None
    mx=statistics.mean(x);my=statistics.mean(y)
    return sum((p-mx)*(q-my) for p,q in zip(x,y))/n/(sx*sy)


def diversity_score(strategy_returns,decision_symbols=None):
    keys=sorted((strategy_returns or {}).keys());corrs=[];overlaps=[];pairs=[];decision_symbols=decision_symbols or {}
    for i,a in enumerate(keys):
        for b in keys[i+1:]:
            c=_corr(strategy_returns.get(a,[]),strategy_returns.get(b,[]))
            sa=set(decision_symbols.get(a,[]) or []);sb=set(decision_symbols.get(b,[]) or [])
            overlap=(len(sa&sb)/len(sa|sb)) if (sa|sb) else None
            if c is not None:corrs.append(abs(c))
            if overlap is not None:overlaps.append(overlap)
            pairs.append({'a':a,'b':b,'abs_correlation':abs(c) if c is not None else None,'decision_overlap':overlap})
    if not pairs:return {'score':None,'clone_risk':'UNKNOWN','pairs':[],'real_trading':False}
    corr=statistics.mean(corrs) if corrs else .5;over=statistics.mean(overlaps) if overlaps else .5
    score=clamp(100-60*corr-40*over);risk='HIGH' if score<35 else ('MEDIUM' if score<60 else 'LOW')
    return {'score':score,'clone_risk':risk,'mean_abs_correlation':corr,'mean_decision_overlap':over,'pairs':pairs,'real_trading':False}


def stability_score(stress_impacts=None,perturbation_results=None):
    impacts=[abs(float(x)) for x in (stress_impacts or []) if _f(x) is not None]
    pert=[float(x) for x in (perturbation_results or []) if _f(x) is not None]
    if not impacts and not pert:return {'stability_score':None,'status':'INSUFFICIENT_EVIDENCE','real_trading':False}
    stress_score=clamp(100-(statistics.mean(impacts)*350 if impacts else 0)-(max(impacts)*250 if impacts else 0)) if impacts else 50
    if len(pert)>=2:
        denom=max(abs(statistics.mean(pert)),1e-9);cv=statistics.pstdev(pert)/denom;pert_score=clamp(100-cv*100)
    else:pert_score=50
    return {'stability_score':.65*stress_score+.35*pert_score,'stress_score':stress_score,'perturbation_score':pert_score,
            'stress_cases':len(impacts),'perturbations':len(pert),'status':'AVAILABLE','real_trading':False}


def data_quality_score(*,freshness=None,benchmark_coverage=None,cost_coverage=None,pit_verified=None,
                       provider_consensus=None,forward_integrity=None,corporate_action_coverage=None):
    checks={};weighted=[]
    def add(name,value,weight):
        if value is None:checks[name]='UNKNOWN';return
        v=clamp(value*100 if isinstance(value,(int,float)) and value<=1 else value);checks[name]=v;weighted.append((v,weight))
    add('freshness',freshness,.20);add('benchmark_coverage',benchmark_coverage,.16);add('cost_coverage',cost_coverage,.16)
    add('pit_verified',1.0 if pit_verified is True else (0.0 if pit_verified is False else None),.16)
    add('provider_consensus',1.0 if provider_consensus is True else (0.0 if provider_consensus is False else None),.10)
    add('forward_integrity',1.0 if forward_integrity is True else (0.0 if forward_integrity is False else None),.16)
    add('corporate_action_coverage',corporate_action_coverage,.06)
    if not weighted:return {'score':None,'status':'INSUFFICIENT_EVIDENCE','checks':checks,'real_trading':False}
    den=sum(w for _,w in weighted);score=sum(v*w for v,w in weighted)/den
    status='GOOD' if score>=85 else ('DEGRADED' if score>=65 else 'BLOCKED')
    return {'score':score,'status':status,'checks':checks,'coverage_weight':den,'real_trading':False}


def counterfactual_quality(records):
    """Summarize explicitly supplied counterfactuals; never manufactures prices."""
    diffs=[];avoided=[]
    for r in records or []:
        actual=_f(r.get('actual_return_pct'));cf=_f(r.get('counterfactual_return_pct'))
        if actual is None or cf is None:continue
        diffs.append(actual-cf);avoided.append(cf<actual)
    if not diffs:return {'n':0,'mean_value_added_pct':None,'positive_value_rate':None,'real_trading':False}
    return {'n':len(diffs),'mean_value_added_pct':statistics.mean(diffs),'positive_value_rate':sum(avoided)/len(avoided),
            'ci95':confidence_interval(diffs),'real_trading':False}


def opportunity_369(opportunities):
    """Auditable 3-6-9 grouping from supplied scores; no recommendation is invented."""
    rows=[dict(x) for x in opportunities or []]
    def score(r,key,default=-1e18):
        v=_f(r.get(key));return v if v is not None else default
    high=sorted(rows,key=lambda r:(score(r,'confidence'),score(r,'score')),reverse=True)[:3]
    rr=sorted(rows,key=lambda r:(score(r,'risk_adjusted_score',score(r,'score')),score(r,'confidence')),reverse=True)[:6]
    promising=sorted(rows,key=lambda r:(score(r,'potential_score',score(r,'score')),score(r,'confidence')),reverse=True)[:9]
    return {'high_confidence_3':high,'risk_return_6':rr,'promising_9':promising,
            'counts':{'input':len(rows),'3':len(high),'6':len(rr),'9':len(promising)},'real_trading':False}


def quality_gate(*,decision_metrics=None,data_quality=None,calibration=None,benchmark=None,
                 stability=None,anti_overfitting=None,transfer=None,min_mature_decisions=8):
    d=decision_metrics or {};dq=data_quality or {};cal=calibration or {};bm=benchmark or {};st=stability or {};ao=anti_overfitting or {};tr=transfer or {}
    checks={
        'mature_decisions':int(d.get('mature_decisions') or 0)>=int(min_mature_decisions),
        'data_quality':_f(dq.get('score'),0)>=70,
        'calibration':cal.get('status') in ('PASS','AVAILABLE') or (_f(cal.get('brier')) is not None and _f(cal.get('brier'))<=.25),
        'benchmark':_f(bm.get('coverage'),0)>=.75,
        'stability':_f(st.get('stability_score'),0)>=45,
        'anti_overfitting':_f(ao.get('score'),0)>=50,
        'historical_live_transfer':_f(tr.get('score'),0)>=45,
    }
    return {'passed':all(checks.values()),'checks':checks,'failed':[k for k,v in checks.items() if not v],
            'automatic_live_promotion':False,'can_trade':False,'real_trading':False}
