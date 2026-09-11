"""Operational pre-1.6 PAPER evaluation aggregator.

This module joins decision outcomes, League history, forward validation, benchmark,
calibration, turnover, stability and data quality without manufacturing missing
evidence.  Missing evidence is a blocker, never a neutral success. REAL_TRADING=false.
"""
from __future__ import annotations

import math
import re
from datetime import datetime, timezone

from radar_calibration_health_v1 import calibration_health
from radar_league_governance_v2 import quality_readiness, champion_degradation
from radar_multi_benchmark_v1 import compare_benchmarks, benchmark_gate
from radar_multiwindow_ranking_v1 import multiwindow_performance, multidimensional_ranking
from radar_pre160_evaluation_v1 import (
    data_quality_score, horizon_quality, regime_generalization, stability_score,
    opportunity_369, quality_gate,
)
from radar_promotion_attribution_v1 import confidence_calibration
from radar_turnover_cost_governor_v1 import turnover_cost_gate

REAL_TRADING=False
_CONF_RE=re.compile(r'confidence\s+([01](?:\.\d+)?)',re.I)


def _f(value,default=None):
    try:
        x=float(value)
        return x if math.isfinite(x) else default
    except (TypeError,ValueError):return default


def _dt(value):
    if not value:return None
    try:
        d=datetime.fromisoformat(str(value).replace('Z','+00:00'))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:return None


def _confidence_from_decision(row):
    value=_f((row or {}).get('confidence'))
    if value is not None:return max(0.0,min(1.0,value))
    payload=(row or {}).get('payload') if isinstance((row or {}).get('payload'),dict) else {}
    value=_f(payload.get('confidence'))
    if value is not None:return max(0.0,min(1.0,value))
    reason=str((row or {}).get('entry_reason') or payload.get('entry_reason') or '')
    match=_CONF_RE.search(reason)
    return max(0.0,min(1.0,float(match.group(1)))) if match else None


def prospective_decisions(durable,competitor_key):
    rows=[]
    for row in (durable or {}).get('decisions') or []:
        if str(row.get('competitor_key'))!=str(competitor_key) or row.get('forward_eligible') is not True:continue
        item=dict(row)
        payload=item.get('payload') if isinstance(item.get('payload'),dict) else {}
        for key in ('entry_reason','exit_reason','entry_capital','exit_value_net','qty','entry_price','exit_price'):
            if item.get(key) is None and payload.get(key) is not None:item[key]=payload[key]
        rows.append(item)
    return rows


def calibration_scorecard(rows,benchmark_coverage=0.0,cost_coverage=0.0):
    records=[]
    for row in rows or []:
        conf=_confidence_from_decision(row)
        pnl=_f(row.get('realized_pnl'))
        if conf is None or pnl is None:continue
        records.append({'confidence':conf,'hit':pnl>0})
    cal=confidence_calibration(records)
    error=cal.get('brier')
    health=calibration_health(
        mature_forward_n=cal.get('n',0),calibration_error=error,
        benchmark_coverage=benchmark_coverage,cost_coverage=cost_coverage,
        backfilled_n=0,
    )
    score=None if error is None else max(0.0,min(100.0,(1.0-float(error))*100.0))
    return {'records':records,'brier':error,'hit_rate':cal.get('hit_rate'),'score':score,
            'status':health.get('status'),'blockers':health.get('blockers') or [],'real_trading':False}


def primary_benchmark_reference(forward_records,integrity_verified=False):
    normalized=[]
    for row in forward_records or []:
        item=dict(row);ret=_f(item.get('net_return',item.get('net_return_pct',item.get('return_pct'))))
        bench=_f(item.get('benchmark_return'))
        item['return_pct']=ret;item['net_return_pct']=ret;item['immutable']=integrity_verified is True
        item['matured']=item.get('matured') is True
        item['benchmarks']={'primary':bench} if bench is not None else {}
        normalized.append(item)
    summary=compare_benchmarks(normalized,benchmark_keys=['primary'])
    gate=benchmark_gate(summary,min_coverage=.95)
    row=(summary.get('benchmarks') or [{}])[0]
    return {'coverage':row.get('coverage',0.0),'mean_excess_pct':row.get('mean_excess_pct'),
            'status':row.get('status'),'gate':gate,'integrity_verified':integrity_verified is True,
            'real_trading':False}


def competitor_vs_champion_benchmark(competitor,champion):
    c=list((competitor or {}).get('daily_equity_30d') or []);h=list((champion or {}).get('daily_equity_30d') or [])
    cm={str(x.get('date') or x.get('day'))[:10]:x for x in c};hm={str(x.get('date') or x.get('day'))[:10]:x for x in h}
    common=[]
    for day in sorted(set(cm)&set(hm)):
        cv=_f(cm[day].get('normalized_equity',cm[day].get('equity')));hv=_f(hm[day].get('normalized_equity',hm[day].get('equity')))
        if cv is not None and hv is not None and hv>0:common.append((cv,hv))
    if len(common)<2:return {'status':'INSUFFICIENT_EVIDENCE','observed_days':len(common),'excess_return_pct':None,'score':None,'real_trading':False}
    c0,h0=common[0];c1,h1=common[-1]
    cr=(c1/c0-1)*100 if c0>0 else None;hr=(h1/h0-1)*100 if h0>0 else None
    excess=(cr-hr) if cr is not None and hr is not None else None
    score=None if excess is None else max(0.0,min(100.0,50.0+excess*5.0))
    return {'status':'AVAILABLE','observed_days':len(common),'competitor_return_pct':cr,
            'champion_return_pct':hr,'excess_return_pct':excess,'score':score,'real_trading':False}


def turnover_scorecard(closed_decisions,current_equity):
    equity=_f(current_equity)
    rows=list(closed_decisions or [])
    gross=sum(max(0.0,_f(x.get('entry_capital'),0.0) or 0.0)+max(0.0,_f(x.get('exit_value_net'),0.0) or 0.0) for x in rows)
    costs=sum(max(0.0,_f(x.get('costs'),0.0) or 0.0) for x in rows)
    turnover=(gross/(2.0*equity)) if equity and equity>0 else None
    gross_return=sum((_f(x.get('realized_pnl'),0.0) or 0.0) for x in rows)
    edge_bps=(gross_return/equity*10000.0) if equity and equity>0 else None
    cost_bps=(costs/equity*10000.0) if equity and equity>0 else None
    gate=turnover_cost_gate(proposed_turnover_pct=turnover if turnover is not None else 0.0,
                            estimated_cost_bps=cost_bps,expected_return_bps=edge_bps)
    if turnover is None:
        gate=dict(gate);gate['status']='BLOCKED';gate['blockers']=list(dict.fromkeys((gate.get('blockers') or [])+['EQUITY_NOT_VERIFIED']))
    return {'turnover_pct':turnover,'estimated_cost_bps':cost_bps,'realized_edge_bps':edge_bps,
            'gate':gate,'real_trading':False}


def stress_scorecard(stress_impacts=None,perturbation_results=None):
    if not stress_impacts and not perturbation_results:
        return {'status':'INSUFFICIENT_EXPOSURE_EVIDENCE','stability_score':None,'real_trading':False}
    return stability_score(stress_impacts or [],perturbation_results or [])


def evidence_maturity(durable,capture_started_at=None):
    decisions=list((durable or {}).get('decisions') or [])
    prospective=sum(x.get('forward_eligible') is True for x in decisions)
    derived=sum(x.get('forward_eligible') is not True for x in decisions)
    start=_dt(capture_started_at or (durable or {}).get('capture_started_at'))
    days=max(0,(datetime.now(timezone.utc)-start).days) if start else 0
    return {'capture_started_at':start.isoformat() if start else None,'observed_runtime_days':days,
            'prospective_closed_decisions':prospective,'derived_preexisting_decisions':derived,
            'status':'PROSPECTIVE_ACCUMULATING' if start else 'NOT_STARTED','real_trading':False}


def enrich_scorecards(base_evaluations,league,forward_records,validation,durable=None,
                      stress_by_competitor=None,regime_records_by_competitor=None):
    """Return enriched competitor scorecards while preserving every missing-data blocker."""
    league=league or {};validation=validation or {};durable=durable or {};stress_by_competitor=stress_by_competitor or {};regime_records_by_competitor=regime_records_by_competitor or {}
    leaderboard={str(x.get('competitor_key')):x for x in league.get('leaderboard') or []}
    champion_key=str(league.get('champion_key') or 'champion');champion=leaderboard.get(champion_key,{})
    gate_evidence=validation.get('paper_gate_evidence') or {}
    integrity_verified=gate_evidence.get('oos_pass') is True
    bm_reference=primary_benchmark_reference(forward_records,integrity_verified=integrity_verified)
    benchmark_coverage=_f(gate_evidence.get('benchmark_coverage'),bm_reference.get('coverage',0.0)) or 0.0
    cost_coverage=_f(gate_evidence.get('cost_coverage'),0.0) or 0.0
    market=validation.get('market_telemetry') or {}
    coverage=_f(market.get('assets_observed'));expected=_f(market.get('assets_expected'))
    freshness=(coverage/expected) if coverage is not None and expected and expected>0 else None
    dq=data_quality_score(freshness=freshness,benchmark_coverage=benchmark_coverage,cost_coverage=cost_coverage,
                          pit_verified=integrity_verified,forward_integrity=integrity_verified)
    out=[]
    for base in base_evaluations or []:
        row=dict(base);key=str(row.get('competitor_key'));league_row=leaderboard.get(key,{})
        prospective=prospective_decisions(durable,key)
        comp_bm=competitor_vs_champion_benchmark(league_row,champion) if key!=champion_key else {
            'status':'CASH_REFERENCE_ONLY','observed_days':len(league_row.get('daily_equity_30d') or []),
            'excess_return_pct':league_row.get('period_change_pct'),'score':None,'real_trading':False}
        calibration=calibration_scorecard(prospective,benchmark_coverage,cost_coverage)
        stress=stress_scorecard(**(stress_by_competitor.get(key) or {}))
        regimes=regime_generalization(regime_records_by_competitor.get(key) or [])
        horizons=horizon_quality([{**x,'immutable':integrity_verified} for x in (forward_records or [])])
        closed=(row.get('closed_decisions') or (row.get('decision_outcomes') or {}).get('closed') or [])
        turnover=turnover_scorecard(closed,league_row.get('current_equity'))
        dm=row.get('decision_metrics') or {};anti_luck=_f(dm.get('anti_luck_score'),0.0) or 0.0
        calibration_score=_f(calibration.get('score'),0.0) if calibration.get('status')=='PASS' else 0.0
        stability_value=_f(stress.get('stability_score'),0.0) if stress.get('status') not in ('INSUFFICIENT_EXPOSURE_EVIDENCE','INSUFFICIENT_EVIDENCE') else 0.0
        benchmark_score=_f(comp_bm.get('score'),0.0) if comp_bm.get('status')=='AVAILABLE' else 0.0
        readiness=quality_readiness(
            league_row,champion,common_days=int((league.get('best_promotion_watch') or {}).get('common_days') or 0),
            persistence_score=_f((league.get('best_promotion_watch') or {}).get('persistence_score'),0.0) or 0.0,
            benchmark_score=benchmark_score,calibration_score=calibration_score,
            stability_score=stability_value,anti_luck_score=anti_luck,
        ) if key!=champion_key else {'eligible':False,'promotion_scope':'SIMULATION_LEAGUE_ONLY','real_trading':False}
        blockers=[]
        if not integrity_verified:blockers.append('FORWARD_INTEGRITY_NOT_VERIFIED')
        if comp_bm.get('status')!='AVAILABLE' and key!=champion_key:blockers.append('COMPETITOR_BENCHMARK_INSUFFICIENT')
        if calibration.get('status')!='PASS':blockers.append('CALIBRATION_NOT_MATURE')
        if stress.get('stability_score') is None:blockers.append('STRESS_EXPOSURES_NOT_VERIFIED')
        if regimes.get('generalization_score') is None:blockers.append('REGIME_GENERALIZATION_NOT_MATURE')
        if (turnover.get('gate') or {}).get('status')!='PASS':blockers.extend((turnover.get('gate') or {}).get('blockers') or [])
        readiness=dict(readiness);readiness['evidence_blockers']=list(dict.fromkeys(blockers));readiness['eligible']=bool(readiness.get('eligible')) and not blockers
        row.update({'prospective_decisions':prospective,'benchmark_reference':bm_reference,'competitor_benchmark':comp_bm,
                    'calibration':calibration,'stress_stability':stress,'regime_generalization':regimes,'horizon_quality':horizons,
                    'turnover_cost':turnover,'data_quality':dq,'promotion_v2':readiness,
                    'multiwindow':multiwindow_performance(league_row.get('daily_equity_30d') or []),
                    'stability_score':stress.get('stability_score'),'data_quality_score':dq.get('score'),
                    'promotion_readiness':readiness.get('readiness'),'can_trade':False,'real_trading':False})
        out.append(row)
    champion_reference=None
    if champion:
        series=champion.get('daily_equity_30d') or []
        if len(series)>=2:
            first=series[0];last=series[-1]
            champion_reference={'v_score':first.get('v_score'),'v_confidence':first.get('v_confidence'),
                                'max_drawdown_pct':first.get('drawdown_pct',0),'period_change_pct':0}
            current={'v_score':last.get('v_score',champion.get('v_score')),'v_confidence':last.get('v_confidence',champion.get('v_confidence')),
                     'max_drawdown_pct':champion.get('max_drawdown_pct'),'period_change_pct':champion.get('period_change_pct')}
            best=max((_f(x.get('promotion_readiness'),0.0) or 0.0 for x in out if str(x.get('competitor_key'))!=champion_key),default=0.0)
            degradation=champion_degradation(champion_reference,current,challenger_readiness=best)
        else:degradation={'degraded':False,'status':'INSUFFICIENT_EVIDENCE','automatic_demotion':False,'real_trading':False}
    else:degradation={'degraded':False,'status':'CHAMPION_NOT_FOUND','automatic_demotion':False,'real_trading':False}
    return {'scorecards':out,'champion_degradation':degradation,'benchmark_reference':bm_reference,
            'data_quality':dq,'evidence_maturity':evidence_maturity(durable),
            'rankings':{mode:multidimensional_ranking(out,mode) for mode in ('quality','v','capital','drawdown','readiness','risk_adjusted')},
            'automatic_promotion':False,'automatic_demotion':False,'can_trade':False,'real_trading':False}


def opportunities_369(operational):
    screened=list(((operational or {}).get('universe') or {}).get('screened') or [])
    return opportunity_369(screened)
