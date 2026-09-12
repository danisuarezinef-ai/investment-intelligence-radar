"""Prospective statistical validity controls for tasks 241-260.

All promotion-relevant outputs fail closed when sample maturity is insufficient.
"""
from __future__ import annotations

import math
from collections import Counter, defaultdict
from statistics import mean, pstdev

REAL_TRADING = False
STATES=frozenset({'PASS','PENDING_SAMPLE','PENDING_TIME','NOT_VERIFIED','FAILED'})
HORIZONS=('1d','1w','1m','3m')


def _task(i,state,detail,*,critical=False,evidence=None):
    if state not in STATES: raise ValueError(state)
    x={'task':int(i),'state':state,'detail':str(detail),'critical':bool(critical)}
    if evidence is not None:x['evidence']=evidence
    return x


def effective_sample_size(weights_or_corr) -> float:
    """Conservative ESS. Accepts normalized-ish observation weights or pairwise correlations."""
    xs=[float(x) for x in (weights_or_corr or [])]
    if not xs:return 0.0
    if all(0 <= x <= 1 for x in xs) and sum(xs) > 0:
        s=sum(xs); sq=sum(x*x for x in xs)
        return (s*s/sq) if sq else 0.0
    n=len(xs); rho=max(-0.99,min(0.99,mean(xs)))
    return max(1.0, n*(1-rho)/(1+rho))


def calibration_metrics(rows: list[dict], bins=10) -> dict:
    valid=[]
    for r in rows or []:
        try:p=float(r['probability']); y=1.0 if bool(r['outcome']) else 0.0
        except Exception:continue
        if 0 <= p <= 1:valid.append((p,y))
    if not valid:return {'n':0,'brier':None,'ece':None,'bins':[],'real_trading':False}
    brier=mean((p-y)**2 for p,y in valid); bucket=defaultdict(list)
    for p,y in valid:bucket[min(bins-1,int(p*bins))].append((p,y))
    rows_out=[]; ece=0.0
    for b,vals in sorted(bucket.items()):
        cp=mean(p for p,_ in vals); oy=mean(y for _,y in vals); w=len(vals)/len(valid); ece += w*abs(cp-oy)
        rows_out.append({'bin':b,'n':len(vals),'predicted':cp,'observed':oy})
    return {'n':len(valid),'brier':brier,'ece':ece,'bins':rows_out,'real_trading':False}


def uncertainty_rank(rows: list[dict]) -> list[dict]:
    out=[]
    for r in rows or []:
        try:mu=float(r.get('expected_return')); sigma=max(0.0,float(r.get('uncertainty',0.0))); tail=max(0.0,float(r.get('tail_risk',0.0)))
        except Exception:continue
        score=mu-0.75*sigma-0.50*tail
        x=dict(r);x['uncertainty_adjusted_score']=score;out.append(x)
    return sorted(out,key=lambda x:x['uncertainty_adjusted_score'],reverse=True)


def return_interval(values: list[float], z=1.96) -> dict:
    xs=[float(x) for x in (values or [])]
    if len(xs)<2:return {'n':len(xs),'mean':xs[0] if xs else None,'low':None,'high':None,'real_trading':False}
    m=mean(xs);sd=pstdev(xs);se=sd/math.sqrt(len(xs));return {'n':len(xs),'mean':m,'low':m-z*se,'high':m+z*se,'real_trading':False}


def tail_risk(values: list[float], alpha=0.05) -> dict:
    xs=sorted(float(x) for x in (values or []))
    if not xs:return {'n':0,'var':None,'expected_shortfall':None,'real_trading':False}
    k=max(1,int(math.ceil(len(xs)*alpha)));tail=xs[:k]
    return {'n':len(xs),'var':tail[-1],'expected_shortfall':mean(tail),'alpha':alpha,'real_trading':False}


def signal_decay(points: list[dict]) -> dict:
    vals=[]
    for r in points or []:
        try:age=float(r['age']); value=abs(float(r['signal']))
        except Exception:continue
        if age>=0 and value>0:vals.append((age,value))
    if len(vals)<2:return {'status':'PENDING_SAMPLE','half_life':None,'n':len(vals),'real_trading':False}
    vals=sorted(vals); initial=vals[0][1]; target=initial/2
    hit=next((age for age,v in vals if v<=target),None)
    return {'status':'PASS' if hit is not None else 'PENDING_TIME','half_life':hit,'n':len(vals),'real_trading':False}


def benjamini_hochberg(p_values: list[float], alpha=0.05) -> dict:
    vals=sorted((float(p),i) for i,p in enumerate(p_values or []) if 0 <= float(p) <= 1)
    cutoff=None
    m=len(vals)
    for rank,(p,_) in enumerate(vals,1):
        if p <= alpha*rank/max(1,m):cutoff=p
    rejected=[i for p,i in vals if cutoff is not None and p<=cutoff]
    return {'m':m,'cutoff':cutoff,'rejected_indices':rejected,'real_trading':False}


def deflated_score(raw_score: float, trials: int, sample_size: float) -> float:
    penalty=math.sqrt(max(0.0,2.0*math.log(max(1,int(trials))))/max(1.0,float(sample_size)))
    return float(raw_score)-penalty


def _balance(rows,key,min_cells=2):
    counts=Counter(str(r.get(key) or 'UNKNOWN') for r in rows or [] if isinstance(r,dict))
    known={k:v for k,v in counts.items() if k!='UNKNOWN'}
    if len(known)<min_cells:return 'PENDING_SAMPLE',known
    ratio=max(known.values())/max(1,min(known.values()))
    return ('PASS' if ratio<=4 else 'FAILED'),known


def build_statistical_tasks(*, evidence:dict, runtime:dict, samples:dict|None=None)->dict:
    evidence=evidence or {}; runtime=runtime or {}; s=samples or {};tasks={}
    closes=s.get('forward_closes') or []
    horizons=Counter(str(r.get('horizon') or '') for r in closes if isinstance(r,dict) and r.get('matured') is True)
    tasks[241]=_task(241,'PASS' if all(horizons.get(h,0)>0 for h in HORIZONS) else 'PENDING_SAMPLE','strictly separate matured 1d/1w/1m/3m outcomes',critical=True,evidence=dict(horizons))

    quality=[max(0.0,min(1.0,float(r.get('quality',1.0)))) for r in closes if isinstance(r,dict)]
    tasks[242]=_task(242,'PASS' if quality and min(quality)>=0 else 'PENDING_SAMPLE','sample-quality weights retained instead of counting all closes equally')
    ess=effective_sample_size(quality)
    tasks[243]=_task(243,'PASS' if ess>=20 else 'PENDING_SAMPLE','effective sample size accounts for unequal/correlated evidence',evidence={'ess':ess})

    st,counts=_balance(closes,'regime');tasks[244]=_task(244,st,'regime-balanced prospective evaluation',evidence=counts)
    st,counts=_balance(closes,'sector');tasks[245]=_task(245,st,'sector-balanced evaluation',evidence=counts)
    assets=Counter(str(r.get('symbol') or '') for r in closes if r.get('symbol'))
    tasks[246]=_task(246,'PASS' if len(assets)>=10 and max(assets.values())/max(1,sum(assets.values()))<=0.35 else 'PENDING_SAMPLE','asset-level generalization versus memorization',evidence={'assets':len(assets)})
    periods=Counter(str(r.get('period') or '') for r in closes if r.get('period'))
    tasks[247]=_task(247,'PASS' if len(periods)>=3 else 'PENDING_TIME','temporal generalization across distinct periods',evidence={'periods':len(periods)})
    markets=Counter(str(r.get('market') or '') for r in closes if r.get('market'))
    tasks[248]=_task(248,'PASS' if len(markets)>=2 else 'PENDING_SAMPLE','cross-market transfer',evidence={'markets':len(markets)})

    cal=calibration_metrics(s.get('calibration_rows') or [])
    tasks[249]=_task(249,'PASS' if cal['n']>=50 and cal['ece'] is not None else 'PENDING_SAMPLE','prospective calibration engine',critical=True,evidence={'n':cal['n'],'brier':cal['brier'],'ece':cal['ece']})
    hist=s.get('calibration_history') or []
    tasks[250]=_task(250,'PASS' if len(hist)>=3 else 'PENDING_TIME','persistent reliability diagrams / calibration history',evidence={'snapshots':len(hist)})
    components=s.get('confidence_components') or {}
    req={'model','data','regime','consensus'}
    tasks[251]=_task(251,'PASS' if req.issubset(components) else 'NOT_VERIFIED','confidence decomposition: model/data/regime/consensus')
    ranked=uncertainty_rank(s.get('opportunities') or [])
    tasks[252]=_task(252,'PASS' if ranked else 'PENDING_SAMPLE','uncertainty-aware 3-6-9 ranking',evidence={'ranked':len(ranked)})

    returns=[float(x) for x in (s.get('returns') or [])]
    ri=return_interval(returns);tasks[253]=_task(253,'PASS' if ri['low'] is not None else 'PENDING_SAMPLE','expected-return intervals, not point estimates only',evidence=ri)
    tr=tail_risk(returns);tasks[254]=_task(254,'PASS' if tr['expected_shortfall'] is not None and len(returns)>=20 else 'PENDING_SAMPLE','tail-risk / expected-shortfall estimate',evidence=tr)
    decay=signal_decay(s.get('signal_decay_points') or []);tasks[255]=_task(255,decay['status'],'prediction-decay measurement',evidence=decay)
    tasks[256]=_task(256,decay['status'],'signal half-life estimation',evidence={'half_life':decay.get('half_life')})

    attrib=s.get('alpha_attribution') or {}
    tasks[257]=_task(257,'PASS' if attrib and abs(sum(float(v) for v in attrib.values())-float(s.get('observed_alpha',sum(float(v) for v in attrib.values()))))<1e-6 else 'PENDING_SAMPLE','alpha attribution by source/family')
    pvals=[float(x) for x in (s.get('candidate_p_values') or [])]
    bh=benjamini_hochberg(pvals);tasks[258]=_task(258,'PASS' if bh['m']>0 else 'PENDING_SAMPLE','false-discovery guard across explored variants',critical=True,evidence={'tested':bh['m'],'discoveries':len(bh['rejected_indices'])})
    tasks[259]=_task(259,'PASS' if bh['m']>1 else 'PENDING_SAMPLE','multiple-hypothesis correction',critical=True,evidence={'cutoff':bh['cutoff']})
    raw=s.get('raw_performance_score');trials=s.get('strategy_trials')
    if raw is None or trials is None: ds=None
    else: ds=deflated_score(float(raw),int(trials),max(1.0,ess))
    tasks[260]=_task(260,'PASS' if ds is not None else 'PENDING_SAMPLE','deflated performance score penalizes search breadth',critical=True,evidence={'deflated_score':ds,'ess':ess,'trials':trials})

    return {'status':'PRE160_STATISTICAL_VALIDITY_V7','tasks':{str(k):v for k,v in tasks.items()},
            'calibration':cal,'uncertainty_ranking':ranked[:9],'automatic_promotion':False,'can_trade':False,'real_trading':False}
