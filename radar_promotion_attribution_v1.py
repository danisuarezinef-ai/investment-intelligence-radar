"""Promotion and attribution primitives for Investment Intelligence Radar.

All gates are evidence-based and fail closed. Passing a gate never enables real
trading; operational enablement remains a separate explicit human action.
"""
from __future__ import annotations
import math, statistics

REAL_TRADING=False
PROMOTION_POLICY_VERSION='v1'
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

def _i(x,default=0):
    try:return int(x)
    except (TypeError,ValueError):return default

def _bool01(x):
    if x is True or x == 1:return 1.0
    if x is False or x == 0:return 0.0
    if isinstance(x,str):
        v=x.strip().lower()
        if v in ('true','1','yes','y','win','hit','positive'):return 1.0
        if v in ('false','0','no','n','loss','miss','negative'):return 0.0
    return None

def _compound_pct(values):
    factor=1.0
    for v in values:factor*=1.0+v/100.0
    return (factor-1.0)*100.0

def promotion_gate(evidence,policy=None):
    """Evaluate predeclared shadow->paper/live-readiness evidence.

    Missing inputs fail the relevant criterion. `ready_for_live_review` means
    only that evidence is sufficient for human review, never permission to trade.
    """
    evidence=evidence or {}
    p=dict(DEFAULT_PROMOTION_POLICY);p.update(policy or {})
    checks={
      'forward_duration':_f(evidence.get('forward_days'),-1)>=p['min_forward_days'],
      'matured_sample':_i(evidence.get('matured_predictions'),0)>=p['min_matured_predictions'],
      'decision_sample':_i(evidence.get('decisions'),0)>=p['min_decisions'],
      'drawdown':abs(_f(evidence.get('max_drawdown_pct'),math.inf))<=p['max_drawdown_pct'],
      'calibration':_f(evidence.get('brier'),math.inf)<=p['max_brier'],
      'hit_rate':_f(evidence.get('hit_rate'),-math.inf)>=p['min_hit_rate'],
      'benchmark_alpha':_f(evidence.get('excess_return_pct'),-math.inf)>=p['min_excess_return_pct'],
      'temporal_breadth':_i(evidence.get('positive_months'),0)>=p['min_positive_months'],
      'ledger_integrity':evidence.get('ledger_integrity') is True,
      'pit_verified':evidence.get('pit_verified') is True,
      'costs_included':evidence.get('costs_included') is True,
    }
    failed=[k for k,v in checks.items() if not v]
    return {'checks':checks,'failed':failed,'ready_for_live_review':not failed,
            'auto_promote':False,'can_trade':False,'real_trading':False,
            'policy_version':PROMOTION_POLICY_VERSION,'policy':p}

def confidence_calibration(records):
    """Brier score and hit-rate from immutable matured prediction records."""
    vals=[];invalid=0
    for r in records or []:
        c=_f(r.get('confidence'));y=_bool01(r.get('hit'))
        if c is None or y is None:
            invalid+=1;continue
        c=max(0.0,min(1.0,c));vals.append((c,y))
    if not vals:return {'n':0,'invalid':invalid,'brier':None,'hit_rate':None}
    return {'n':len(vals),'invalid':invalid,
            'brier':statistics.mean((c-y)**2 for c,y in vals),
            'hit_rate':statistics.mean(y for _,y in vals)}

def performance_attribution(periods):
    """Linked realized return attribution from explicitly supplied components.

    Portfolio and benchmark returns are geometrically linked across periods.
    Missing realized returns make the corresponding aggregate unavailable rather
    than silently converting missing evidence to zero. Component attribution is
    reported additively because no cross-period linking convention is assumed.
    """
    periods=list(periods or [])
    keys=('selection','timing','sizing','market_beta','sector','fx','costs','cash_drag')
    totals={k:0.0 for k in keys};known=0
    portfolio_vals=[];benchmark_vals=[];missing_portfolio=missing_benchmark=0
    for r in periods:
        row_known=False
        for k in keys:
            v=_f(r.get(k))
            if v is not None:totals[k]+=v;row_known=True
        known+=int(row_known)
        p=_f(r.get('portfolio_return'));b=_f(r.get('benchmark_return'))
        if p is None:missing_portfolio+=1
        else:portfolio_vals.append(p)
        if b is None:missing_benchmark+=1
        else:benchmark_vals.append(b)
    realized=_compound_pct(portfolio_vals) if periods and missing_portfolio==0 else None
    benchmark=_compound_pct(benchmark_vals) if periods and missing_benchmark==0 else None
    excess=(realized-benchmark) if realized is not None and benchmark is not None else None
    explained=sum(totals.values()) if known else None
    unexplained=(realized-explained) if realized is not None and explained is not None else None
    return {'periods':len(periods),'periods_with_components':known,'components':totals,
            'component_linking':'additive_supplied_components',
            'return_linking':'geometric',
            'portfolio_return':realized,'benchmark_return':benchmark,'excess_return':excess,
            'explained_return':explained,'unexplained':unexplained,
            'complete_portfolio_returns':missing_portfolio==0 and bool(periods),
            'complete_benchmark_returns':missing_benchmark==0 and bool(periods),
            'missing_portfolio_returns':missing_portfolio,
            'missing_benchmark_returns':missing_benchmark,
            'real_trading':False}

def degradation_check(reference,current,limits=None):
    """Detect deterioration without inventing missing baseline/current evidence."""
    reference=reference or {};current=current or {}
    lim={'hit_rate_drop':.08,'brier_increase':.05,'excess_return_drop_pct':5.0,'drawdown_worsening_pct':5.0};lim.update(limits or {})
    pairs={
      'hit_rate_drop':(_f(reference.get('hit_rate')),_f(current.get('hit_rate')),'drop'),
      'brier_increase':(_f(reference.get('brier')),_f(current.get('brier')),'increase'),
      'excess_return_drop_pct':(_f(reference.get('excess_return_pct')),_f(current.get('excess_return_pct')),'drop'),
      'drawdown_worsening_pct':(_f(reference.get('max_drawdown_pct')),_f(current.get('max_drawdown_pct')),'drawdown'),
    }
    deltas={};breaches={};missing=[]
    for k,(a,b,mode) in pairs.items():
        if a is None or b is None:
            deltas[k]=None;breaches[k]=None;missing.append(k);continue
        if mode=='drop':d=a-b
        elif mode=='increase':d=b-a
        else:d=abs(b)-abs(a)
        deltas[k]=d;breaches[k]=d>lim[k]
    comparable=[v for v in breaches.values() if v is not None]
    return {'degraded':any(comparable) if comparable else None,
            'evidence_complete':not missing,'missing_metrics':missing,
            'breaches':breaches,'deltas':deltas,'limits':lim,
            'automatic_model_retirement':False,'real_trading':False}
