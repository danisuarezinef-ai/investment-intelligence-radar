"""Thesis Intelligence primitives. Immutable evidence-oriented records; no trade execution."""
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
import hashlib, json

def now(): return datetime.now(timezone.utc).isoformat()

def fingerprint(x): return hashlib.sha256(json.dumps(x,sort_keys=True,separators=(',',':')).encode()).hexdigest()

@dataclass
class Thesis:
    symbol:str; horizon:str; thesis:str
    catalysts:list=field(default_factory=list); risks:list=field(default_factory=list)
    strengthen_if:list=field(default_factory=list); weaken_if:list=field(default_factory=list); kill_if:list=field(default_factory=list)
    valuation_context:dict=field(default_factory=dict); causal_chain:list=field(default_factory=list)
    created_at:str=field(default_factory=now)
    def snapshot(self):
        p=asdict(self);p['fingerprint']=fingerprint(p);p['real_trading']=False;return p

def evaluate_thesis(thesis, observed_facts):
    text=' '.join(str(x).lower() for x in observed_facts)
    hits=lambda rules:[r for r in rules if str(r).lower() in text]
    killed=hits(thesis.kill_if);weak=hits(thesis.weaken_if);strong=hits(thesis.strengthen_if)
    if killed: state='INVALIDATED'
    elif len(weak)>len(strong): state='WEAKENED'
    elif strong: state='STRENGTHENED'
    else: state='UNCHANGED'
    return {'state':state,'kill_hits':killed,'weaken_hits':weak,'strengthen_hits':strong,'evaluated_at':now(),'real_trading':False}

def attribution(component_scores, outcome):
    """Signed normalized responsibility; diagnostic, not causal proof."""
    vals={k:float(v) for k,v in component_scores.items()};den=sum(abs(v) for v in vals.values()) or 1
    direction=1 if float(outcome)>=0 else -1
    return {k:round(direction*v/den,6) for k,v in vals.items()}

def counterfactual_delta(full_objective, without_component_objective):
    return float(full_objective)-float(without_component_objective)

FAILURE_PATTERNS={
 'late_momentum_chase':'strong momentum with deteriorating forward reward/risk',
 'narrative_overvaluation':'positive narrative overwhelmed by valuation risk',
 'regime_mismatch':'signal learned in one regime fails after regime transition',
 'correlation_as_causality':'correlated feature treated as causal without evidence',
 'false_precision':'high conviction despite weak data or model disagreement',
 'thesis_drift':'recommendation changes without an explicit thesis event',
}
