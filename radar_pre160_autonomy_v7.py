"""Autonomous model governance for tasks 261-270.

All outputs are PAPER/SHADOW governance only.  Automatic live promotion, release and
real-money execution are deliberately impossible here.
"""
from __future__ import annotations

import math
from collections import defaultdict
from statistics import mean

REAL_TRADING=False
STATES=frozenset({'PASS','PENDING_SAMPLE','PENDING_TIME','NOT_VERIFIED','FAILED'})


def _task(i,state,detail,*,critical=False,evidence=None):
    if state not in STATES:raise ValueError(state)
    x={'task':int(i),'state':state,'detail':str(detail),'critical':bool(critical)}
    if evidence is not None:x['evidence']=evidence
    return x


def challenger_incubation(candidate:dict, *, min_forward_n=30, min_days=14)->dict:
    n=int(candidate.get('forward_n') or 0);days=float(candidate.get('forward_days') or 0)
    forward_only=candidate.get('forward_only') is True;mature=candidate.get('matured_only') is True
    eligible=n>=min_forward_n and days>=min_days and forward_only and mature and candidate.get('backfilled') is not True
    return {'eligible':eligible,'forward_n':n,'forward_days':days,'automatic_promotion':False,'real_trading':False}


def degradation_detector(series:list[float], *, window=10, tolerance=-0.002)->dict:
    xs=[float(x) for x in (series or [])]
    if len(xs)<window*2:return {'status':'PENDING_SAMPLE','degraded':False,'real_trading':False}
    prev=mean(xs[-2*window:-window]);cur=mean(xs[-window:]);delta=cur-prev
    return {'status':'PASS','degraded':delta<float(tolerance),'previous':prev,'current':cur,'delta':delta,'real_trading':False}


def shadow_ensemble(predictions:list[dict])->dict:
    valid=[]
    for r in predictions or []:
        try:w=max(0.0,float(r.get('weight',1.0)));p=float(r['prediction'])
        except Exception:continue
        if w>0:valid.append((w,p,str(r.get('model') or 'UNKNOWN')))
    if not valid:return {'status':'PENDING_SAMPLE','prediction':None,'models':0,'authority':'SHADOW_ONLY','real_trading':False}
    total=sum(w for w,_,_ in valid);pred=sum(w*p for w,p,_ in valid)/total
    return {'status':'PASS','prediction':pred,'models':len(valid),'authority':'SHADOW_ONLY','real_trading':False}


def diversity_score(vectors:list[list[float]])->float:
    if len(vectors)<2:return 0.0
    d=[]
    for i,a in enumerate(vectors):
        for b in vectors[i+1:]:
            n=min(len(a),len(b))
            if not n:continue
            d.append(sum(abs(float(a[j])-float(b[j])) for j in range(n))/n)
    return mean(d) if d else 0.0


def correlation_penalty(correlation:float, *, start=0.70)->float:
    r=abs(float(correlation))
    if r<=start:return 0.0
    return min(1.0,(r-start)/(1.0-start))


def route_model(candidates:list[dict], context:dict)->dict:
    """Contextual routing with no authority to promote or trade."""
    scored=[]
    for c in candidates or []:
        if c.get('eligible') is not True:continue
        score=float(c.get('base_score') or 0.0)
        if c.get('regime')==context.get('regime'):score+=0.25
        if c.get('horizon')==context.get('horizon'):score+=0.25
        if c.get('asset_class')==context.get('asset_class'):score+=0.15
        score-=0.50*float(c.get('uncertainty') or 0.0)
        scored.append((score,c))
    if not scored:return {'status':'ABSTAIN','model':None,'automatic_promotion':False,'real_trading':False}
    scored.sort(key=lambda x:x[0],reverse=True)
    return {'status':'ROUTED','model':scored[0][1].get('model_version'),'score':scored[0][0],'automatic_promotion':False,'real_trading':False}


def abstention_decision(*, expected_edge:float|None, uncertainty:float|None, tail_risk:float|None,
                        data_ok:bool, calibration_ok:bool, min_edge=0.005, max_uncertainty=0.03, max_tail=0.05)->dict:
    blockers=[]
    if not data_ok:blockers.append('DATA_NOT_VERIFIED')
    if not calibration_ok:blockers.append('CALIBRATION_NOT_MATURE')
    if expected_edge is None or float(expected_edge)<min_edge:blockers.append('EDGE_TOO_SMALL')
    if uncertainty is None or float(uncertainty)>max_uncertainty:blockers.append('UNCERTAINTY_TOO_HIGH')
    if tail_risk is None or float(tail_risk)>max_tail:blockers.append('TAIL_RISK_TOO_HIGH')
    return {'decision':'ABSTAIN' if blockers else 'PAPER_CANDIDATE','blockers':blockers,
            'live_execution_allowed':False,'can_trade':False,'real_trading':False}


def master_gate(task_groups:list[dict], *, windows_version='1.5.28')->dict:
    tasks={}
    for group in task_groups or []:tasks.update(group.get('tasks') or {})
    critical_failed=[k for k,v in tasks.items() if isinstance(v,dict) and v.get('critical') and v.get('state')=='FAILED']
    critical_pending=[k for k,v in tasks.items() if isinstance(v,dict) and v.get('critical') and v.get('state')!='PASS']
    all_pass=bool(tasks) and all((v or {}).get('state')=='PASS' for v in tasks.values())
    status='READY_FOR_MANUAL_1_6_REVIEW' if all_pass and not critical_pending else 'BLOCKED_PRE160'
    return {'status':status,'tasks':len(tasks),'critical_failed':critical_failed,'critical_pending':critical_pending,
            'stable_windows_version':windows_version,'candidate_version':'1.6.0','manual_review_only':True,
            'setup_allowed':False,'setup_built':False,'automatic_release':False,'automatic_promotion':False,
            'automatic_demotion':False,'live_execution_allowed':False,'can_trade':False,'real_trading':False}


def build_autonomy_tasks(*, runtime:dict, evidence:dict, candidates:list[dict]|None=None,
                         champion_history:list[float]|None=None, shadow_predictions:list[dict]|None=None,
                         diversity_vectors:list[list[float]]|None=None, correlations:list[float]|None=None,
                         routing_context:dict|None=None, task_groups:list[dict]|None=None)->dict:
    runtime=runtime or {};evidence=evidence or {};candidates=candidates or [];tasks={}
    champion=runtime.get('champion_key') or runtime.get('champion')
    comparable=[c for c in candidates if c.get('forward_only') is True and c.get('matured_only') is True and c.get('backfilled') is not True]
    tasks[261]=_task(261,'PASS' if champion and comparable else 'PENDING_SAMPLE','Champion–Challenger competition uses comparable forward-only evidence',critical=True,evidence={'comparable_challengers':len(comparable)})
    incubated=[challenger_incubation(c) for c in candidates]
    tasks[262]=_task(262,'PASS' if any(x['eligible'] for x in incubated) else 'PENDING_SAMPLE','challenger incubation floor before promotion eligibility',critical=True)
    deg=degradation_detector(champion_history or [])
    tasks[263]=_task(263,deg['status'],'sustained Champion degradation detector without single-sample reaction',evidence=deg)
    ens=shadow_ensemble(shadow_predictions or [])
    tasks[264]=_task(264,ens['status'],'shadow ensemble has no execution authority',evidence={'models':ens.get('models'),'authority':ens.get('authority')})
    div=diversity_score(diversity_vectors or [])
    tasks[265]=_task(265,'PASS' if len(diversity_vectors or [])>=2 and div>0 else 'PENDING_SAMPLE','diversity reward favors non-clone information',evidence={'diversity_score':div})
    cors=[abs(float(x)) for x in (correlations or [])]
    penalties=[correlation_penalty(x) for x in cors]
    tasks[266]=_task(266,'PASS' if cors else 'PENDING_SAMPLE','correlation penalty for redundant strategies',evidence={'max_penalty':max(penalties) if penalties else None})

    contexts=defaultdict(list)
    for c in candidates:
        if c.get('forward_only') is True and c.get('matured_only') is True:
            contexts[(c.get('regime'),c.get('horizon'),c.get('asset_class'))].append(c)
    tasks[267]=_task(267,'PASS' if len(contexts)>=3 else 'PENDING_SAMPLE','meta-learner training table spans regime×horizon×asset contexts',evidence={'contexts':len(contexts)})
    route=route_model(candidates,routing_context or {})
    tasks[268]=_task(268,'PASS' if route['status']=='ROUTED' else 'PENDING_SAMPLE','dynamic model routing uses only eligible specialists',evidence=route)

    cal=(evidence.get('calibration') or {}).get('status')=='MATURE'
    fresh=(evidence.get('freshness') or {}).get('status')=='FRESH'
    best=next(iter(sorted(candidates,key=lambda c:float(c.get('base_score') or 0),reverse=True)),{}) if candidates else {}
    abstain=abstention_decision(expected_edge=best.get('expected_edge'),uncertainty=best.get('uncertainty'),tail_risk=best.get('tail_risk'),data_ok=fresh,calibration_ok=cal)
    tasks[269]=_task(269,'PASS','abstention engine is authoritative over PAPER candidacy and always blocks live execution',critical=True,evidence=abstain)

    preliminary={'status':'PRE160_AUTONOMY_V7','tasks':{str(k):v for k,v in tasks.items()},'real_trading':False}
    gate=master_gate((task_groups or [])+[preliminary])
    tasks[270]=_task(270,'PASS' if gate['status']=='READY_FOR_MANUAL_1_6_REVIEW' else 'NOT_VERIFIED','master pre-1.6 gate across tasks 1-270; manual review only',critical=True,evidence={'status':gate['status'],'critical_pending':gate['critical_pending']})
    preliminary['tasks']={str(k):v for k,v in tasks.items()};preliminary['master_gate']=master_gate((task_groups or [])+[preliminary])
    preliminary.update({'automatic_release':False,'automatic_promotion':False,'automatic_demotion':False,'can_trade':False,'real_trading':False})
    return preliminary
