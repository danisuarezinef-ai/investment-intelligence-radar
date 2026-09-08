"""Conservative portfolio risk controls for Champion shadow/paper execution.

The engine is deliberately fail-closed for new allocations. It never executes
real trades and does not infer missing risk evidence.
"""
from __future__ import annotations
import math, statistics

REAL_TRADING=False
DEFAULT_LIMITS={
    'max_position':0.20,
    'max_invested':0.70,
    'max_positions':5,
    'max_drawdown_pct':-12.0,
    'soft_drawdown_pct':-7.0,
    'min_confidence':0.42,
    'min_allocation':0.02,
}

def clamp(x,a=0.0,b=1.0):return max(a,min(b,float(x)))

def adaptive_risk_multiplier(confidence,drawdown_pct,volatility=None,limits=None):
    l=dict(DEFAULT_LIMITS);l.update(limits or {})
    conf=clamp(confidence);dd=float(drawdown_pct or 0)
    if dd<=l['max_drawdown_pct']:return 0.0
    conf_mult=clamp((conf-l['min_confidence'])/max(1e-9,1-l['min_confidence']))
    dd_mult=1.0
    if dd<0:dd_mult=clamp((dd-l['max_drawdown_pct'])/max(1e-9,0-l['max_drawdown_pct']))
    if dd<=l['soft_drawdown_pct']:dd_mult*=0.5
    vol_mult=1.0
    if volatility is not None:
        v=max(0.0,float(volatility));vol_mult=1.0/(1.0+4.0*v)
    return clamp(conf_mult*dd_mult*vol_mult)

def portfolio_risk_gate(status,decision,volatility=None,limits=None):
    """Return an auditable allocation cap; zero means no new risk may be added."""
    l=dict(DEFAULT_LIMITS);l.update(limits or {})
    total=max(0.0,float(status.get('total') or 0));invested=max(0.0,float(status.get('invested') or 0));cash=max(0.0,float(status.get('cash') or 0))
    dd=float(status.get('max_drawdown_pct') or 0);positions=status.get('positions') or []
    conf=clamp(decision.get('confidence') or 0);requested=clamp(decision.get('allocation_fraction') or 0)
    reasons=[]
    if decision.get('action')!='PAPER_BUY_CANDIDATE':reasons.append('action_not_buy_candidate')
    if conf<l['min_confidence']:reasons.append('confidence_below_floor')
    if len(positions)>=int(l['max_positions']):reasons.append('position_limit')
    if dd<=float(l['max_drawdown_pct']):reasons.append('drawdown_hard_stop')
    if total<=0 or cash<=0:reasons.append('capital_unavailable')
    mult=adaptive_risk_multiplier(conf,dd,volatility,l)
    gross_cap=max(0.0,total*l['max_invested']-invested)
    position_cap=total*l['max_position']
    requested_cash=total*requested*mult
    allowed=0.0 if reasons else min(requested_cash,gross_cap,position_cap,cash*.97)
    return {'allowed_budget':max(0.0,allowed),'risk_multiplier':mult,'requested_fraction':requested,
            'max_position':l['max_position'],'max_invested':l['max_invested'],'drawdown_pct':dd,
            'blocked':allowed<=0,'reasons':reasons,'real_trading':False}

def expected_shortfall(returns,alpha=.05):
    vals=sorted(float(x) for x in returns if x is not None)
    if not vals:return None
    n=max(1,math.ceil(len(vals)*clamp(alpha,1e-6,1.0)));return statistics.mean(vals[:n])
