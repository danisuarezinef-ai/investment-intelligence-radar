"""Evidence-adjusted PAPER strategy quality score (v-score).

The v-score is a simulation monitoring metric, not a promise of future returns.
It compresses observed result quality, risk, consistency and evidence into 0..400.
Low evidence contracts the score toward neutral v200. Mature closed PAPER decisions
replace daily-up/down proxies when enough decision evidence exists. It grants no
model or live-trading authority.
"""
from __future__ import annotations

import math
import statistics
from collections import OrderedDict

from radar_core import con

REAL_TRADING = False
V_MIN = 0
V_MAX = 400
V_NEUTRAL = 200

WEIGHTS = OrderedDict((
    ('decision_quality', 0.30),
    ('risk_adjusted_return', 0.22),
    ('risk_control', 0.18),
    ('consistency', 0.12),
    ('generalization', 0.10),
    ('evidence', 0.08),
))


def clamp(value, low=0.0, high=100.0):
    return max(float(low), min(float(high), float(value)))


def _smooth_score(value, scale):
    try:
        return clamp(50.0 + 50.0 * math.tanh(float(value) / float(scale)))
    except (TypeError, ValueError, ZeroDivisionError):
        return 50.0


def _finite(value, default=None):
    try:
        x=float(value)
        return x if math.isfinite(x) else default
    except (TypeError,ValueError):
        return default


def _daily_values(series):
    values = []
    for raw in series or []:
        if not isinstance(raw, dict):
            continue
        try:value=float(raw.get('equity'))
        except (TypeError,ValueError):continue
        if value>0:values.append((str(raw.get('date') or raw.get('day') or '')[:10],value))
    return values


def _daily_returns(series):
    vals=_daily_values(series);out=[]
    for (_,previous),(_,current) in zip(vals,vals[1:]):
        if previous>0:out.append(current/previous-1.0)
    return out


def _band(v):
    value=int(v)
    if value<120:return 'MUY DEFICIENTE'
    if value<180:return 'DÉBIL'
    if value<220:return 'NEUTRA'
    if value<260:return 'COMPETENTE'
    if value<300:return 'FUERTE'
    if value<340:return 'MUY FUERTE'
    return 'EXCEPCIONAL'


def _decision_outcome_quality(metrics, fallback_hit, fallback_return):
    """0..100 realized-decision quality; tiny samples stay close to fallback."""
    m=metrics or {};n=max(0,int(m.get('mature_decisions') or 0))
    if n<3:
        return None
    hit=m.get('hit_rate'); hit_score=50.0 if hit is None else clamp(float(hit)*100.0)
    mean_return=_finite(m.get('mean_return_pct'),0.0);return_score=_smooth_score(mean_return,5.0)
    pf=_finite(m.get('profit_factor'))
    pf_score=50.0 if pf is None else _smooth_score(pf-1.0,1.2)
    capital_eff=_finite(m.get('capital_efficiency_pct'),0.0);eff_score=_smooth_score(capital_eff,8.0)
    anti_luck=clamp(m.get('anti_luck_score',50.0))
    error_ratio=_finite(m.get('error_cost_ratio'))
    error_score=50.0 if error_ratio is None else clamp((1.0-error_ratio)*100.0)
    realized=clamp(.25*hit_score+.20*return_score+.18*pf_score+.12*eff_score+.15*anti_luck+.10*error_score)
    # Ramp from 3 to 12 mature decisions to prevent a few lucky closes dominating v.
    authority=min(1.0,max(0.0,(n-2)/10.0))
    fallback=clamp(.62*fallback_hit+.38*fallback_return)
    return clamp((1.0-authority)*fallback+authority*realized)


def compute_v_score(status,daily_series=None,trade_count=0,distinct_symbols=0,
                    target_invested_pct=70.0,decision_metrics=None,risk_metrics=None,
                    abstention=None,regime_metrics=None,benchmark_metrics=None,
                    stress_metrics=None,calibration_metrics=None,turnover_metrics=None):
    """Return an explainable v-score from observed PAPER outcomes only.

    Mature closed decisions supersede daily-direction proxies gradually. Missing
    benchmark/regime/calibration/stress evidence never becomes a positive claim.
    """
    status=status or {};daily=_daily_values(daily_series);returns=_daily_returns(daily_series)
    observed_days=len(daily);up_days=sum(1 for r in returns if r>1e-12);down_days=sum(1 for r in returns if r<-1e-12)
    directional=up_days+down_days;positive_ratio=(up_days/directional) if directional else .5
    initial=float(status.get('initial') or 0.0);total=float(status.get('total') or initial or 0.0)
    period_return_pct=((total/initial)-1.0)*100.0 if initial>0 else 0.0
    return_score=_smooth_score(period_return_pct,8.0)
    sharpe=status.get('sharpe')
    if sharpe is None and len(returns)>=3:
        sd=statistics.pstdev(returns);sharpe=statistics.mean(returns)/sd*math.sqrt(252.0) if sd>1e-12 else 0.0
    sharpe=_finite(sharpe,0.0) or 0.0;sharpe_score=_smooth_score(sharpe,2.0)
    hit_score=100.0*positive_ratio

    realized_quality=_decision_outcome_quality(decision_metrics,hit_score,return_score)
    decision_quality=realized_quality if realized_quality is not None else clamp(.62*hit_score+.38*return_score)
    semantics='REALIZED_CLOSED_PAPER_DECISIONS_PLUS_FALLBACK' if realized_quality is not None else 'OBSERVED_PAPER_DECISION_QUALITY_PROXY'

    abst=(abstention or {}).get('quality')
    if abst is not None and int((abstention or {}).get('evaluated') or 0)>=5:
        decision_quality=clamp(.88*decision_quality+.12*clamp(float(abst)*100.0))
        semantics='REALIZED_CLOSED_AND_ABSTENTION_PAPER_DECISIONS'
    cal=calibration_metrics or {};brier=_finite(cal.get('brier'))
    if brier is not None and int(cal.get('n') or 0)>=10:
        calibration_score=clamp(100.0-(brier*125.0))
        decision_quality=clamp(.90*decision_quality+.10*calibration_score)

    risk_adjusted_return=clamp(.58*return_score+.42*sharpe_score)
    bm=benchmark_metrics or {};excess=_finite(bm.get('mean_excess_pct',bm.get('excess_return_pct')))
    coverage=_finite(bm.get('coverage'),0.0) or 0.0
    if excess is not None and coverage>=.75:
        alpha_score=_smooth_score(excess,5.0)
        risk_adjusted_return=clamp(.78*risk_adjusted_return+.22*alpha_score)

    max_dd=_finite(status.get('max_drawdown_pct',status.get('drawdown_pct')),0.0) or 0.0
    if risk_metrics and risk_metrics.get('max_drawdown_pct') is not None:
        max_dd=min(max_dd,_finite(risk_metrics.get('max_drawdown_pct'),max_dd))
    dd_score=clamp(100.0-abs(min(0.0,max_dd))*4.0)
    invested_pct=(float(status.get('invested') or 0.0)/total*100.0) if total>0 else 0.0
    target=max(1.0,float(target_invested_pct or 70.0));overshoot=max(0.0,invested_pct-target);undershoot=max(0.0,target-invested_pct)
    exposure_score=clamp(100.0-overshoot*5.0-undershoot*.35)
    if risk_metrics and risk_metrics.get('risk_budget_compliance_score') is not None:
        exposure_score=clamp(.45*exposure_score+.55*clamp(risk_metrics['risk_budget_compliance_score']))
    risk_control=clamp(.72*dd_score+.28*exposure_score)
    stress=stress_metrics or {};stress_score=_finite(stress.get('stability_score'))
    if stress_score is not None:
        risk_control=clamp(.85*risk_control+.15*clamp(stress_score))

    if returns:
        vol_pct=statistics.pstdev(returns)*100.0 if len(returns)>1 else abs(returns[0])*100.0
        vol_score=clamp(100.0-vol_pct*9.0)
    else:vol_score=50.0
    consistency=clamp(.62*hit_score+.38*vol_score)
    if decision_metrics and int(decision_metrics.get('mature_decisions') or 0)>=5:
        anti_luck=clamp(decision_metrics.get('anti_luck_score',50.0))
        consistency=clamp(.78*consistency+.22*anti_luck)
    turnover=turnover_metrics or {}
    if turnover.get('status')=='BLOCKED':consistency=clamp(consistency-8.0)

    regime=regime_metrics or {};regime_n=int(regime.get('regimes_evaluated') or 0)
    if regime_n>=2 and regime.get('generalization_score') is not None:
        generalization=clamp(regime['generalization_score']);generalization_status='OBSERVED_REGIME_LINKAGE'
    else:
        breadth=min(max(int(distinct_symbols or 0),0),10)
        generalization=clamp(min(78.0,42.0+breadth*3.0+min(observed_days,18)*.7))
        generalization_status='PROXY_UNTIL_REGIME_LINKAGE'

    marks=int(status.get('marks') or observed_days or 0);trades=max(0,int(trade_count or 0));closed=max(0,int((decision_metrics or {}).get('mature_decisions') or 0))
    evidence=clamp(100.0*(.42*min(observed_days/20.0,1.0)+.18*min(trades/24.0,1.0)+.14*min(marks/120.0,1.0)+.26*min(closed/20.0,1.0)))
    components={'decision_quality':round(decision_quality,2),'risk_adjusted_return':round(risk_adjusted_return,2),
                'risk_control':round(risk_control,2),'consistency':round(consistency,2),
                'generalization':round(generalization,2),'evidence':round(evidence,2)}
    raw_quality=sum(components[k]*WEIGHTS[k] for k in WEIGHTS)
    confidence=clamp(.10+.90*(evidence/100.0),.10,1.0)
    adjusted=50.0+confidence*(raw_quality-50.0);v_score=int(round(clamp(adjusted)*4.0));v_score=max(V_MIN,min(V_MAX,v_score))
    return {'v_score':v_score,'v_band':_band(v_score),'v_confidence':round(confidence,4),
            'v_raw_quality':round(raw_quality,2),'v_adjusted_quality':round(adjusted,2),'v_components':components,
            'observed_days':observed_days,'up_days':up_days,'down_days':down_days,'period_return_pct':round(period_return_pct,4),
            'invested_pct':round(invested_pct,4),'generalization_status':generalization_status,
            'score_semantics':semantics,'decision_metrics':decision_metrics or {},'risk_metrics':risk_metrics or {},
            'automatic_model_promotion':False,'can_trade':False,'real_trading':False}


def competitor_observations(competitor_key,status,target_invested_pct=70.0,limit=180):
    """Load observed marks plus decision-level quality for one PAPER strategy."""
    c=con()
    try:
        if competitor_key=='champion':
            marks=c.execute('select ts,total from champion_paper_marks order by id desc limit ?',(int(limit),)).fetchall()
            trade_rows=c.execute('select symbol from champion_paper_trades order by id desc limit 500').fetchall()
        else:
            marks=c.execute('select ts,total from paper_agent_marks where agent_id=? order by id desc limit ?',(competitor_key,int(limit))).fetchall()
            trade_rows=c.execute('select symbol from paper_agent_trades where agent_id=? order by id desc limit 500',(competitor_key,)).fetchall()
    finally:c.close()
    by_day={}
    for ts,total in reversed(marks):
        day=str(ts or '')[:10]
        try:value=float(total)
        except (TypeError,ValueError):continue
        if day and value>0:by_day[day]=value
    daily=[{'date':day,'equity':value} for day,value in sorted(by_day.items())]
    symbols={str(row[0]) for row in trade_rows if row and row[0]}
    decision=None;risk=None
    try:
        from radar_strategy_evaluation_v1 import competitor_evaluation
        evaluation=competitor_evaluation(competitor_key,status,target_invested_pct)
        decision=evaluation.get('decision_metrics');risk={**(evaluation.get('drawdown_profile') or {}),**(evaluation.get('risk_attribution') or {})}
    except Exception:
        # Observability/evaluation enrichment must never stop the autonomous simulator.
        evaluation=None
    out=compute_v_score(status,daily_series=daily,trade_count=len(trade_rows),distinct_symbols=len(symbols),
                        target_invested_pct=target_invested_pct,decision_metrics=decision,risk_metrics=risk)
    if evaluation is not None:out['strategy_evaluation']=evaluation
    return out
