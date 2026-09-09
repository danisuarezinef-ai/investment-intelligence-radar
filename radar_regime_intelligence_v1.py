"""Regime-aware intelligence v1.

Classifies a supplied point-in-time market state and applies conservative,
reviewable multipliers. It never infers missing market data and cannot trade.
"""
from __future__ import annotations

REAL_TRADING = False


def classify_regime(snapshot):
    s = snapshot or {}
    required = ('volatility_pct', 'trend_pct', 'breadth_pct')
    missing = [k for k in required if s.get(k) is None]
    if missing:
        return {'status':'INSUFFICIENT_EVIDENCE','regime':'UNKNOWN','missing':missing,
                'risk_multiplier':0.0,'confidence_multiplier':0.0,'real_trading':False}
    vol=float(s['volatility_pct']); trend=float(s['trend_pct']); breadth=float(s['breadth_pct'])
    inflation=s.get('inflation_trend')
    if vol >= 30 or (trend <= -10 and breadth <= 35):
        regime='RISK_OFF'; rm=.45; cm=.75
    elif vol >= 22 or trend <= -5:
        regime='DEFENSIVE'; rm=.65; cm=.85
    elif trend >= 8 and breadth >= 60 and vol < 22:
        regime='RISK_ON'; rm=1.0; cm=1.0
    else:
        regime='NEUTRAL'; rm=.8; cm=.9
    if inflation == 'rising' and regime == 'RISK_ON':
        regime='RISK_ON_INFLATIONARY'; rm=.85
    return {'status':'OK','regime':regime,'risk_multiplier':rm,
            'confidence_multiplier':cm,'inputs':{k:s.get(k) for k in required+('inflation_trend',)},
            'real_trading':False}


def apply_regime_to_candidate(candidate, regime_state):
    c=dict(candidate or {}); r=regime_state or {}
    if r.get('status') != 'OK':
        return {**c,'regime_status':'BLOCKED','regime':'UNKNOWN','adjusted_budget':0.0,
                'adjusted_confidence':0.0,'real_trading':False}
    budget=max(0.0,float(c.get('approved_budget') or c.get('requested_budget') or 0.0))
    confidence=max(0.0,min(1.0,float(c.get('confidence') or 0.0)))
    return {**c,'regime_status':'APPLIED','regime':r['regime'],
            'adjusted_budget':budget*float(r['risk_multiplier']),
            'adjusted_confidence':confidence*float(r['confidence_multiplier']),
            'real_trading':False}
