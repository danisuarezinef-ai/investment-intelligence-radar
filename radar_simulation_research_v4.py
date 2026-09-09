"""Strict research protocol for autonomous Simulation Lab experiments.

Historical/simulated evidence is research-only. This module enforces chronological
train/validation/test windows, expanded stress scenarios, multidimensional ranking
and anti-overfitting penalties. It cannot create forward evidence or real orders.
"""
from __future__ import annotations
import copy, math, statistics
from radar_simulation_research_v3 import evaluate_config
from radar_simulation_v2 import _series_by_day

REAL_TRADING=False


def _metric(row,key,default=0.0):
    v=(row or {}).get(key)
    return float(v) if isinstance(v,(int,float)) else float(default)


def chronological_walk_forward(config,days=None,folds=4,min_train=60,validation_days=15,test_days=15):
    days=list(days or _series_by_day()); n=len(days); rows=[]
    need=int(min_train)+int(validation_days)+int(test_days)
    if n<need:
        return {'completed':False,'reason':'INSUFFICIENT_HISTORY','folds':[],'lookahead':False,'real_trading':False}
    start=int(min_train)
    for fold in range(max(1,int(folds))):
        val_start=start; val_end=min(n,val_start+int(validation_days)); test_end=min(n,val_end+int(test_days))
        if val_end-val_start<5 or test_end-val_end<5: break
        train=days[:val_start]; validation=days[val_start:val_end]; test=days[val_end:test_end]
        # evaluate each partition independently; no future rows are visible to earlier partitions
        train_r=evaluate_config(config,train)
        validation_r=evaluate_config(config,train+validation)
        test_r=evaluate_config(config,train+validation+test)
        rows.append({'fold':fold+1,'train_days':len(train),'validation_days':len(validation),'test_days':len(test),
                     'train':train_r,'validation':validation_r,'test':test_r,
                     'train_end':train[-1][0] if train else None,
                     'validation_end':validation[-1][0] if validation else None,
                     'test_end':test[-1][0] if test else None,'lookahead':False})
        start=test_end
        if start>=n: break
    valid=[x for x in rows if x['test'].get('completed')]
    test_returns=[_metric(x['test'],'return_pct') for x in valid]
    test_dd=[abs(_metric(x['test'],'max_drawdown_pct')) for x in valid]
    stability=0.0 if not valid else max(0.0,100.0-(statistics.pstdev(test_returns) if len(test_returns)>1 else 0.0)-statistics.mean(test_dd))
    return {'completed':len(valid)>=2,'folds':rows,'mean_test_return_pct':statistics.mean(test_returns) if test_returns else None,
            'worst_test_drawdown_pct':-max(test_dd) if test_dd else None,'stability_score':stability,
            'lookahead':False,'evidence_class':'SIMULATED_WALK_FORWARD_ONLY','real_trading':False}


def _transform_days(days,scenario):
    rows=copy.deepcopy(list(days)); kind=scenario.get('kind')
    if not rows:return rows
    if kind=='missing_data':
        every=max(2,int(scenario.get('every',5)));out=[]
        for i,(d,p) in enumerate(rows):
            q=dict(p)
            if i%every==0:
                for s in sorted(q)[::3]:q.pop(s,None)
            out.append((d,q))
        return out
    if kind=='gap':
        pct=float(scenario.get('pct',-12))/100.0;idx=len(rows)//2;d,p=rows[idx];rows[idx]=(d,{s:max(.0001,v*(1+pct)) for s,v in p.items()});return rows
    if kind=='sideways':
        first=rows[0][1];return [(d,{s:first.get(s,v) for s,v in p.items()}) for d,p in rows]
    if kind=='volatility':
        amp=float(scenario.get('amp',.12));out=[]
        for i,(d,p) in enumerate(rows):
            k=1+amp if i%2==0 else 1-amp;out.append((d,{s:max(.0001,v*k) for s,v in p.items()}))
        return out
    return rows


def expanded_stress_suite(config,days=None):
    days=list(days or _series_by_day())
    scenarios={
      'base':({},{}),'costs_2x':({}, {'cost_multiplier':2}),'costs_4x':({}, {'cost_multiplier':4}),
      'gap_-12':({'kind':'gap','pct':-12},{}),'volatility':({'kind':'volatility','amp':.12},{}),
      'sideways':({'kind':'sideways'},{}),'missing_data':({'kind':'missing_data','every':5},{}),
      'shock_-20':({}, {'shock_pct':-20})}
    rows={}
    for name,(transform,stress) in scenarios.items():rows[name]=evaluate_config(config,_transform_days(days,transform),stress=stress)
    completed=[r for r in rows.values() if r.get('completed')]
    drawdowns=[abs(_metric(r,'max_drawdown_pct')) for r in completed]
    returns=[_metric(r,'return_pct') for r in completed]
    survival=bool(completed) and all(dd<50 for dd in drawdowns)
    return {'completed':len(completed)==len(rows),'scenarios':rows,'survival_pass':survival,
            'worst_drawdown_pct':-max(drawdowns) if drawdowns else None,'worst_return_pct':min(returns) if returns else None,
            'real_trading':False}


def anti_overfit_gate(walk,stress,max_fold_return_sd=20.0,min_positive_fraction=.5,max_train_test_gap=30.0):
    folds=[x for x in walk.get('folds',[]) if x.get('test',{}).get('completed')]; blockers=[]
    test_returns=[_metric(x['test'],'return_pct') for x in folds]
    train_returns=[_metric(x['train'],'return_pct') for x in folds]
    sd=statistics.pstdev(test_returns) if len(test_returns)>1 else 0.0
    pos=sum(1 for x in test_returns if x>0)/len(test_returns) if test_returns else 0.0
    gaps=[abs(a-b) for a,b in zip(train_returns,test_returns)]
    if len(folds)<2:blockers.append('TOO_FEW_WALK_FORWARD_FOLDS')
    if sd>float(max_fold_return_sd):blockers.append('UNSTABLE_ACROSS_TEST_FOLDS')
    if pos<float(min_positive_fraction):blockers.append('LOW_POSITIVE_FOLD_FRACTION')
    if gaps and statistics.mean(gaps)>float(max_train_test_gap):blockers.append('TRAIN_TEST_DIVERGENCE')
    if not stress.get('survival_pass'):blockers.append('STRESS_SURVIVAL_FAILED')
    return {'status':'PASS_RESEARCH' if not blockers else 'REJECT','blockers':blockers,'fold_return_sd':sd,
            'positive_fold_fraction':pos,'mean_train_test_gap':statistics.mean(gaps) if gaps else None,
            'eligible_next_stage':'SHADOW_REVIEW' if not blockers else 'GRAVEYARD',
            'can_promote_to_paper':False,'real_trading':False}


def multidimensional_score(base,walk,stress,gate):
    if not base.get('completed') or gate.get('status')!='PASS_RESEARCH':return -1e9
    ret=_metric(base,'return_pct');dd=abs(_metric(base,'max_drawdown_pct'));sharpe=_metric(base,'sharpe');costs=_metric(base,'costs')
    stability=_metric(walk,'stability_score');worst=abs(_metric(stress,'worst_drawdown_pct'))
    # survival first: reward robustness, penalize tail risk and costs more than raw return
    return 0.30*ret+0.55*sharpe+0.35*stability-0.80*dd-0.45*worst-0.04*costs


def research_protocol(config,days=None):
    days=list(days or _series_by_day());base=evaluate_config(config,days);walk=chronological_walk_forward(config,days);stress=expanded_stress_suite(config,days);gate=anti_overfit_gate(walk,stress);score=multidimensional_score(base,walk,stress,gate)
    return {'base':base,'walk_forward':walk,'stress':stress,'gate':gate,'research_score':score,
            'evidence_class':'SIMULATED_RESEARCH_ONLY','automatic_live_promotion':False,'real_trading':False}
