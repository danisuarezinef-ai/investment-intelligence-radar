"""Continuous experiment generator for Simulation Lab.

Experiments are hypotheses only. Historical/simulated results never become
forward evidence and never authorize real trading. Generation-dependent design
prevents the brain from exhausting a fixed nine-configuration grid.
"""
from __future__ import annotations
import hashlib,json,random
REAL_TRADING=False

BASELINE={'lookback_fast':20,'lookback_slow':60,'fast_weight':0.65,'slow_weight':0.35,'exit_momentum':-5.0,'cost_multiplier':1.0}


def _candidate_config(rng,baseline,index):
    cfg=dict(baseline)
    # Deterministic pseudo-random exploration: reproducible for a generation but
    # open-ended across generations. Constraints keep configurations sensible.
    fast=rng.randint(8,40)
    slow=rng.randint(max(45,fast+15),120)
    fw=round(rng.uniform(.45,.82),2)
    cfg.update({'lookback_fast':fast,'lookback_slow':slow,'fast_weight':fw,
                'slow_weight':round(1.0-fw,2),'exit_momentum':round(rng.uniform(-10.0,-2.0),1),
                'cost_multiplier':round(rng.choice([1.0,1.0,1.25,1.5,2.0]),2)})
    # Every fourth hypothesis is an explicit cost-resilience probe.
    if index%4==3:cfg['cost_multiplier']=2.0
    return cfg


def generate_experiments(generation=1, baseline=None, count=12):
    g=max(1,int(generation));b={**BASELINE,**(baseline or {})};candidates=[];seen=set()
    rng=random.Random(0x5241444152+g*104729)
    attempts=0
    while len(candidates)<max(1,int(count)) and attempts<max(50,int(count)*10):
        attempts+=1;cfg=_candidate_config(rng,b,len(candidates));raw=json.dumps(cfg,sort_keys=True,separators=(',',':'))
        h=hashlib.sha256(raw.encode()).hexdigest()
        if h in seen:continue
        seen.add(h);candidates.append({'experiment_id':f'g{g}-{h[:12]}','name':f'generated_g{g}_{len(candidates)+1:02d}','generation':g,'configuration':cfg,'evidence_class':'SIMULATED_HISTORICAL_ONLY','eligible_for_forward_promotion':False,'real_trading':False})
    return candidates


def rank_experiments(results):
    """Survival-first research ranking; does not promote anything."""
    ranked=[]
    for r in results or []:
        if not r.get('completed'):continue
        ret=float(r.get('return_pct') or 0);alpha=float(r.get('alpha_pct') or 0);dd=abs(float(r.get('max_drawdown_pct') or 0));costs=float(r.get('costs') or 0);stability=float(r.get('stability_score') or 0)
        score=alpha+0.25*ret+0.50*stability-0.75*dd-0.05*costs
        ranked.append({**r,'research_score':score,'promotion':'SHADOW_CANDIDATE_REVIEW_ONLY','real_trading':False})
    return sorted(ranked,key=lambda x:x['research_score'],reverse=True)
