"""Promotion and attribution primitives for Investment Intelligence Radar.

All gates are evidence-based and fail closed. Passing a gate never enables real
trading; operational enablement remains a separate explicit human action.
"""
from __future__ import annotations
import math, statistics

REAL_TRADING=False
DEFAULT_PROMOTION_POLICY={
    'min_forward_days':90,
    'min_matured_predictions':100,
    'min_decisions':40,
    'max_drawdown_pct':10.0,
    'max_brier':0.20,
    'min_hit_rate':0.52,
    'min_excess_return_pct':0.0,
    'min_positive_months':3,
}

def _f(x,default=None):
    try:return float(x)
    except (TypeError,ValueError):return default

def promotion_gate(evidence,policy=None):
    """Evaluate predeclared shadow->paper/live-readiness evidence.

    Missing inputs fail the relevant criterion. `ready_for_live_review` means
    only that evidence is sufficient for human review, never permission to trade.
    """
    p=dict(DEFAULT_PROMOTION_POLICY);p.update(policy or {})
    checks={
      'forward_duration':_f(evidence.get('forward_days'),-1)>=p['min_forward_days'],
      'matured_sample':int(evidence.get('matured_predictions') or 0)>=p['min_matured_predictions'],
      'decision_sample':int(evidence.get('decisions') or 0)>=p['min_decisions'],
      'drawdown':abs(_f(evidence.get('max_drawdown_pct'),math.inf))<=p['max_drawdown_pct'],
      'calibration':_f(evidence.get('brier'),math.inf)<=p['max_brier'],
      'hit_rate':_f(evidence.get('hit_rate'),-math.inf)>=p['min_hit_rate'],
      'benchmark_alpha':_f(evidence.get('excess_return_pct'),-math.inf)>=p['min_excess_return_pct'],
      'temporal_breadth':int(evidence.get('positive_months') or 0)>=p['min_positive_months'],
      'ledger_integrity':evidence.get('ledger_integrity') is True,
      'pit_verified':evidence.get('pit_verified') is True,
      'costs_included':evidence.get('costs_included') is True,
    }
    failed=[k for k,v in checks.items() if not v]
    return {'checks':checks,'failed':failed,'ready_for_live_review':not failed,
            'auto_promote':False,'can_trade':False,'real_trading':False,'policy':p}

def confidence_calibration(records):
    """Brier score and hit-rate from immutable matured prediction records."""
    vals=[]
    for r in records:
        c=_f(r.get('confidence'));hit=r.get('hit')
        if c is None or hit is None:continue
        c=max(0.0,min(1.0,c));y=1.0 if bool(hit) else 0.0;vals.append((c,y))
    if not vals:return {'n':0,'brier':None,'hit_rate':None}
    return {'n':len(vals),'brier':statistics.mean((c-y)**2 for c,y in vals),'hit_rate':statistics.mean(y for _,y in vals)}

def performance_attribution(periods):
    """Additive attribution from supplied realized components; never invents them."""
    keys=('selection','timing','sizing','market_beta','sector','fx','costs','cash_drag')
    totals={k:0.0 for k in keys};known=0
    for r in periods:
        row_known=False
        for k in keys:
            v=_f(r.get(k))
            if v is not None:totals[k]+=v;row_known=True
        known+=int(row_known)
    explained=sum(totals.values())
    realized=sum(_f(r.get('portfolio_return'),0.0) for r in periods)
    benchmark=sum(_f(r.get('benchmark_return'),0.0) for r in periods)
    return {'periods':len(periods),'periods_with_components':known,'components':totals,
            'explained_return':explained,'portfolio_return':realized,'benchmark_return':benchmark,
            'excess_return':realized-benchmark,'unexplained':realized-explained,'real_trading':False}

def degradation_check(reference,current,limits=None):
    """Detect meaningful deterioration without auto-changing production weights."""
    lim={'hit_rate_drop':.08,'brier_increase':.05,'excess_return_drop_pct':5.0,'drawdown_worsening_pct':5.0};lim.update(limits or {})
    deltas={
      'hit_rate_drop':_f(reference.get('hit_rate'),0)-_f(current.get('hit_rate'),0),
      'brier_increase':_f(current.get('brier'),0)-_f(reference.get('brier'),0),
      'excess_return_drop_pct':_f(reference.get('excess_return_pct'),0)-_f(current.get('excess_return_pct'),0),
      'drawdown_worsening_pct':abs(_f(current.get('max_drawdown_pct'),0))-abs(_f(reference.get('max_drawdown_pct'),0)),
    }
    breaches={k:deltas[k]>lim[k] for k in deltas}
    return {'degraded':any(breaches.values()),'breaches':breaches,'deltas':deltas,'limits':lim,
            'automatic_model_retirement':False,'real_trading':False}
