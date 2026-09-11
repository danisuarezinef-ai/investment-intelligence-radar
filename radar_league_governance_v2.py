"""Quality-aware PAPER League governance v2.

This is a simulation-governance layer only. It distinguishes capital leadership from
quality leadership and explicitly penalizes luck concentration, instability,
uncalibrated confidence and excess risk. It can recommend a PAPER League role change;
it cannot promote production models or enable real trading.
"""
from __future__ import annotations

import math

REAL_TRADING=False
POLICY_VERSION='dynamic_quality_v2'


def clamp(x,lo=0.0,hi=100.0):
    try:return max(lo,min(hi,float(x)))
    except (TypeError,ValueError):return lo


def _value(obj,key,default=None):
    v=(obj or {}).get(key,default)
    try:return float(v)
    except (TypeError,ValueError):return default


def dynamic_required_days_v2(*,v_gap=0,confidence=0,equity_gap_pct=0,stability=50,anti_luck=50,calibration=50):
    gap=float(v_gap or 0);conf=max(0.0,min(1.0,float(confidence or 0)));eq=float(equity_gap_pct or 0)
    quality=(clamp(stability)+clamp(anti_luck)+clamp(calibration))/300.0
    days=3.0+(1-conf)*16.0+(1-quality)*10.0+max(0.0,8.0-gap)*.7+max(0.0,1.0-eq)*1.5
    return max(2,min(40,int(math.ceil(days))))


def quality_readiness(challenger,champion,*,common_days=0,persistence_score=0,
                      benchmark_score=None,calibration_score=None,stability_score=None,
                      anti_luck_score=None,risk_guard_pp=10.0,threshold=88.0):
    ch=challenger or {};cp=champion or {}
    cv=_value(ch,'v_score',200);pv=_value(cp,'v_score',200);v_gap=cv-pv
    ce=_value(ch,'current_equity',_value(ch,'normalized_equity',0)) or 0
    pe=_value(cp,'current_equity',_value(cp,'normalized_equity',0)) or 0
    equity_gap=(ce/pe-1)*100 if pe>0 else 0.0
    confidence=min(_value(ch,'v_confidence',0) or 0,_value(cp,'v_confidence',0) or 0)
    cdd=_value(ch,'max_drawdown_pct',_value(ch,'drawdown_pct',0)) or 0;pdd=_value(cp,'max_drawdown_pct',_value(cp,'drawdown_pct',0)) or 0
    risk_ok=cdd>=pdd-float(risk_guard_pp)
    dd_excess=max(0.0,abs(cdd)-abs(pdd));risk_score=clamp(100-dd_excess*7)
    b=50.0 if benchmark_score is None else clamp(benchmark_score)
    cal=50.0 if calibration_score is None else clamp(calibration_score)
    stability=50.0 if stability_score is None else clamp(stability_score)
    anti_luck=50.0 if anti_luck_score is None else clamp(anti_luck_score)
    quality_adv=clamp(50+v_gap*1.7);performance_adv=clamp(50+equity_gap*4)
    evidence=clamp(min(_value((ch.get('v_components') or {}),'evidence',0) or 0,_value((cp.get('v_components') or {}),'evidence',0) or 0))
    robustness=.25*risk_score+.18*stability+.15*anti_luck+.12*cal+.10*b+.20*clamp(persistence_score)
    readiness=clamp(.28*quality_adv+.22*performance_adv+.22*evidence+.28*robustness)
    required=dynamic_required_days_v2(v_gap=v_gap,confidence=confidence,equity_gap_pct=equity_gap,
                                      stability=stability,anti_luck=anti_luck,calibration=cal)
    gates={
        'readiness':readiness>=float(threshold),
        'v_advantage':v_gap>=4.0,
        'equity_advantage':equity_gap>0,
        'confidence':confidence>=.55,
        'evidence_duration':int(common_days or 0)>=required,
        'risk_guard':risk_ok,
        'anti_luck':anti_luck>=45,
        'stability':stability>=45,
        'calibration':cal>=40,
    }
    eligible=all(gates.values())
    return {'readiness':round(readiness,2),'threshold':float(threshold),'v_gap':round(v_gap,2),
            'equity_gap_pct':round(equity_gap,3),'confidence':round(confidence,4),
            'robustness_score':round(robustness,2),'risk_score':round(risk_score,2),
            'benchmark_score':round(b,2),'calibration_score':round(cal,2),'stability_score':round(stability,2),
            'anti_luck_score':round(anti_luck,2),'common_days':int(common_days or 0),
            'dynamic_required_days':required,'gates':gates,'eligible':eligible,
            'promotion_scope':'SIMULATION_LEAGUE_ONLY','automatic_model_promotion':False,
            'can_trade':False,'real_trading':False,'policy_version':POLICY_VERSION}


def champion_degradation(reference,current,*,challenger_readiness=0):
    """Detect a weakening Champion; this only lowers PAPER review resistance."""
    ref=reference or {};cur=current or {}
    v_drop=(_value(ref,'v_score',200) or 200)-(_value(cur,'v_score',200) or 200)
    dd_worsening=abs(min(0,_value(cur,'max_drawdown_pct',0) or 0))-abs(min(0,_value(ref,'max_drawdown_pct',0) or 0))
    conf_drop=(_value(ref,'v_confidence',0) or 0)-(_value(cur,'v_confidence',0) or 0)
    return_drop=(_value(ref,'period_change_pct',0) or 0)-(_value(cur,'period_change_pct',0) or 0)
    severity=clamp(max(0,v_drop)*1.4+max(0,dd_worsening)*4+max(0,conf_drop)*35+max(0,return_drop)*2)
    degraded=severity>=55
    review_pressure=clamp(.7*severity+.3*clamp(challenger_readiness))
    return {'degraded':degraded,'severity':round(severity,2),'review_pressure':round(review_pressure,2),
            'v_drop':round(v_drop,2),'drawdown_worsening_pp':round(dd_worsening,3),
            'confidence_drop':round(conf_drop,4),'return_drop_pp':round(return_drop,3),
            'automatic_demotion':False,'promotion_scope':'SIMULATION_LEAGUE_ONLY',
            'can_trade':False,'real_trading':False,'policy_version':POLICY_VERSION}
