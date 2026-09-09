"""Continuous experiment generator for Simulation Lab.

Experiments are hypotheses only. Historical/simulated results never become
forward evidence and never authorize real trading.
"""
from __future__ import annotations
import hashlib,json
REAL_TRADING=False

BASELINE={'lookback_fast':20,'lookback_slow':60,'fast_weight':0.65,'slow_weight':0.35,'exit_momentum':-5.0,'cost_multiplier':1.0}


def generate_experiments(generation=1, baseline=None):
    b={**BASELINE,**(baseline or {})}; candidates=[]
    mutations=[('fast_10',{'lookback_fast':10}),('fast_30',{'lookback_fast':30}),('slow_40',{'lookback_slow':40}),('slow_90',{'lookback_slow':90}),('weight_fast_75',{'fast_weight':0.75,'slow_weight':0.25}),('weight_balanced',{'fast_weight':0.50,'slow_weight':0.50}),('exit_tight',{'exit_momentum':-3.0}),('exit_wide',{'exit_momentum':-8.0}),('cost_stress_2x',{'cost_multiplier':2.0})]
    for name,delta in mutations:
        cfg={**b,**delta}; raw=json.dumps(cfg,sort_keys=True,separators=(',',':'))
        candidates.append({'experiment_id':f'g{int(generation)}-'+hashlib.sha256(raw.encode()).hexdigest()[:12],'name':name,'generation':int(generation),'configuration':cfg,'evidence_class':'SIMULATED_HISTORICAL_ONLY','eligible_for_forward_promotion':False,'real_trading':False})
    return candidates


def rank_experiments(results):
    """Survival-first research ranking; does not promote anything."""
    ranked=[]
    for r in results or []:
        if not r.get('completed'):continue
        ret=float(r.get('return_pct') or 0); alpha=float(r.get('alpha_pct') or 0); dd=abs(float(r.get('max_drawdown_pct') or 0)); costs=float(r.get('costs') or 0)
        stability=float(r.get('stability_score') or 0)
        score=alpha+0.25*ret+0.50*stability-0.75*dd-0.05*costs
        ranked.append({**r,'research_score':score,'promotion':'SHADOW_CANDIDATE_REVIEW_ONLY','real_trading':False})
    return sorted(ranked,key=lambda x:x['research_score'],reverse=True)
