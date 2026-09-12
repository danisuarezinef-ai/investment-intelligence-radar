"""Autonomous PAPER priorities 41-60.

Advanced forward-only diagnostics for calibration, confidence, abstention, tail risk,
cost sensitivity, benchmark robustness, decay, 3-6-9 ranking, Champion/Challenger,
ensemble diversity, no-lookahead routing, meta-learning, historical->live transfer,
anti-overfitting, empirical stress and a manual-review promotion gate.

This module is observational/advisory. It cannot trade, release, promote, demote, or
accelerate forward evidence. REAL_TRADING is permanently false here.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone
from statistics import mean, pstdev

from radar_brain_calibration_v2 import (
    abstention_quality,
    calibration_drift,
    calibration_engine_v2,
    confidence_decomposition,
    downside_distribution,
    rank_369,
    signal_decay_by_family,
    uncertainty_decomposition,
)
from radar_brain_competition_v3 import competition_snapshot
import radar_brain_persistence_v1 as persistence

REAL_TRADING=False
SNAPSHOT_KIND='autonomous_learning_41_60_v1'
COMBINED_KIND='autonomous_learning_16_60_v1'
MIN_FORWARD_N=30


def _finite(value):
    try:
        x=float(value)
        return x if math.isfinite(x) else None
    except Exception:
        return None


def _actions(rows):
    return [r for r in (rows or []) if r.get('matured') is True and r.get('natural') is True
            and str(r.get('decision_state') or '').upper() in {'BUY','SELL'}]


def _ci(values):
    xs=[x for x in (_finite(v) for v in values or []) if x is not None]
    if not xs:return {'n':0,'mean':None,'low':None,'high':None}
    m=mean(xs)
    if len(xs)<2:return {'n':1,'mean':m,'low':None,'high':None}
    se=pstdev(xs)/math.sqrt(len(xs))
    return {'n':len(xs),'mean':m,'low':m-1.96*se,'high':m+1.96*se}


def calibration_quality(rows, analytics=None):
    existing=(analytics or {}).get('calibration') if isinstance(analytics,dict) else None
    out=dict(existing or calibration_engine_v2(rows))
    out.update({'forward_only':True,'promotion_authority':False,'real_trading':False})
    return out


def calibration_drift_guard(rows, analytics=None):
    existing=(analytics or {}).get('drift') if isinstance(analytics,dict) else None
    out=dict(existing or calibration_drift(rows))
    out.update({'automatic_recalibration':False,'automatic_promotion':False,'real_trading':False})
    return out


def confidence_uncertainty_guard(rows):
    sample=[r for r in (rows or []) if r.get('matured') is not True][-100:]
    if not sample:
        sample=list(rows or [])[-100:]
    inspected=[]
    for r in sample:
        c=confidence_decomposition(r);u=uncertainty_decomposition(r)
        raw=_finite(r.get('confidence'))
        inspected.append({'prediction_id':r.get('prediction_id'),'symbol':r.get('symbol'),
                          'raw_confidence':raw,'adjusted_confidence':c.get('adjusted_confidence'),
                          'confidence_ceiling':c.get('confidence_ceiling'),
                          'epistemic_proxy':u.get('epistemic_proxy'),'aleatoric_proxy':u.get('aleatoric_proxy')})
    lowered=sum(1 for x in inspected if x['raw_confidence'] is not None and x['adjusted_confidence'] is not None
                and x['adjusted_confidence'] < x['raw_confidence'])
    valid=sum(1 for x in inspected if x['adjusted_confidence'] is not None)
    return {'status':'PASS' if valid>=20 else 'PENDING_SAMPLE','n':len(inspected),'valid_n':valid,
            'confidence_lowered_n':lowered,'fail_closed_ceiling_active':True,
            'uncertainty_is_diagnostic_proxy':True,'empirical_variance_decomposition_claimed':False,
            'examples':inspected[:20],'automatic_strategy_change':False,'real_trading':False}


def abstention_quality_guard(rows, analytics=None):
    existing=(analytics or {}).get('abstention_quality') if isinstance(analytics,dict) else None
    out=dict(existing or abstention_quality(rows))
    out.update({'abstention_can_reduce_paper_exposure':True,'abstention_can_enable_live_trading':False,
                'automatic_threshold_change':False,'real_trading':False})
    return out


def downside_tail_risk(rows):
    actions=[r for r in _actions(rows) if _finite(r.get('net_return')) is not None]
    net=[float(r['net_return']) for r in actions]
    excess=[float(r['excess_return']) for r in actions if _finite(r.get('excess_return')) is not None]
    n=len(net)
    return {'status':'PASS' if n>=MIN_FORWARD_N else 'PENDING_SAMPLE','n':n,
            'net_return':downside_distribution(net),'excess_return':downside_distribution(excess),
            'mean_net_return':mean(net) if net else None,'interval_net_return':_ci(net),
            'risk_authority':'DIAGNOSTIC_ONLY','position_increase_allowed':False,'real_trading':False}


def cost_sensitivity(rows):
    gross=[]
    for r in _actions(rows):
        net=_finite(r.get('net_return'));cost=_finite(r.get('cost'))
        if net is None or cost is None:continue
        gross.append(net+cost)
    scenarios=[]
    for bps in (5,10,20,30,50):
        c=bps/10000.0
        vals=[x-c for x in gross]
        scenarios.append({'round_trip_bps':bps,'n':len(vals),'mean_net_return':mean(vals) if vals else None,
                          'profitable_rate':sum(1 for x in vals if x>0)/len(vals) if vals else None})
    break_even=mean(gross)*10000 if gross else None
    return {'status':'PASS' if len(gross)>=MIN_FORWARD_N else 'PENDING_SAMPLE','n':len(gross),
            'scenarios':scenarios,'break_even_round_trip_bps':break_even,
            'uses_observed_gross_from_net_plus_recorded_cost':True,'synthetic_trades_added':False,
            'automatic_cost_model_change':False,'real_trading':False}


def benchmark_robustness(rows):
    actions=[r for r in _actions(rows) if _finite(r.get('excess_return')) is not None]
    excess=[float(r['excess_return']) for r in actions]
    with_benchmark=[r for r in actions if _finite(r.get('benchmark_return')) is not None]
    ids={str((r.get('outcome') or {}).get('benchmark') or r.get('benchmark') or 'RECORDED_BENCHMARK') for r in with_benchmark}
    coverage=len(with_benchmark)/len(actions) if actions else 0.0
    multi=len(ids)>=2
    return {'status':'PASS' if len(actions)>=MIN_FORWARD_N and coverage>=.95 else 'PENDING_SAMPLE',
            'n':len(actions),'benchmark_coverage':coverage,'benchmark_ids':sorted(ids),
            'mean_excess_return':mean(excess) if excess else None,'interval_excess_return':_ci(excess),
            'positive_excess_rate':sum(1 for x in excess if x>0)/len(excess) if excess else None,
            'multi_benchmark_robustness_verified':multi and len(actions)>=MIN_FORWARD_N,
            'single_benchmark_cannot_prove_multi_benchmark_robustness':not multi,
            'automatic_benchmark_selection':False,'real_trading':False}


def decay_guard(rows, analytics=None):
    existing=(analytics or {}).get('decay') if isinstance(analytics,dict) else None
    out=dict(existing or signal_decay_by_family(rows))
    out.update({'horizon_backfill_allowed':False,'horizon_acceleration_allowed':False,
                'forward_only':True,'real_trading':False})
    return out


def ranking_guard(rows, analytics=None):
    existing=(analytics or {}).get('ranking_369') if isinstance(analytics,dict) else None
    out=dict(existing or rank_369(rows))
    out.update({'ranking_scope':'PAPER_ADVISORY_ONLY','orders_created':False,
                'automatic_execution':False,'real_trading':False})
    return out


def _competition_piece(competition, key):
    if isinstance(competition,dict) and isinstance(competition.get(key),dict):
        out=dict(competition[key]);out['real_trading']=False;return out
    return {'status':'PENDING_SAMPLE','reason':'COMPETITION_SNAPSHOT_UNAVAILABLE','real_trading':False}


def anti_overfit_diagnostic(rows, calibration, routing, transfer, diversity, prior_16_40=None):
    matured=[r for r in (rows or []) if r.get('matured') is True and r.get('natural') is True]
    n=len(matured)
    pit=sum(1 for r in matured if (r.get('quality_checks') or {}).get('pit_valid') is True)
    pit_ratio=pit/n if n else 0.0
    dates=sorted({str(r.get('created_at') or '')[:10] for r in matured if r.get('created_at')})
    days=len(dates)
    cal_ece=_finite(calibration.get('ece'))
    cal_score=0.0 if cal_ece is None else max(0.0,min(1.0,1.0-cal_ece/.25))
    routing_score=1.0 if routing.get('status')=='PASS' and not routing.get('lookahead_violations') else 0.0
    transfer_value=_finite(transfer.get('transfer_score'))
    transfer_score=0.0 if transfer_value is None else max(0.0,min(1.0,(transfer_value+1.0)/2.0))
    model_count=int((diversity or {}).get('model_count') or 0)
    diversity_score=1.0 if model_count>=2 else .25 if model_count==1 else 0.0
    horizon_tasks=(prior_16_40 or {}).get('tasks') or {}
    horizon_score=sum(1 for k in ('36','37','38') if (horizon_tasks.get(k) or {}).get('state')=='PASS')/3.0
    sample_score=min(1.0,n/120.0)*.6+min(1.0,days/30.0)*.4
    components={'pit_integrity':pit_ratio,'calibration':cal_score,'no_lookahead_routing':routing_score,
                'historical_live_transfer':transfer_score,'model_diversity':diversity_score,
                'multi_horizon_maturity':horizon_score,'sample_depth':sample_score}
    weights={'pit_integrity':.20,'calibration':.15,'no_lookahead_routing':.20,
             'historical_live_transfer':.10,'model_diversity':.10,'multi_horizon_maturity':.15,'sample_depth':.10}
    score=100.0*sum(components[k]*weights[k] for k in weights)
    coverage=sum(1 for v in (cal_ece,transfer_value) if v is not None)
    status='PENDING_SAMPLE' if n<MIN_FORWARD_N or coverage<1 else ('PASS' if score>=70 else 'ATTENTION')
    return {'status':status,'score_0_100':round(score,2),'components':components,'weights':weights,
            'matured_n':n,'calendar_days_observed':days,'model_count':model_count,
            'diagnostic_not_formal_proof':True,'cannot_promote_model':True,
            'no_lookahead_required':True,'real_trading':False}


def empirical_stress(rows, cost):
    net=[float(r['net_return']) for r in _actions(rows) if _finite(r.get('net_return')) is not None]
    if not net:
        return {'status':'PENDING_SAMPLE','n':0,'stress_type':'OBSERVED_DISTRIBUTION_ONLY','real_trading':False}
    ordered=sorted(net);k=max(1,int(math.ceil(.10*len(ordered))))
    worst_decile=mean(ordered[:k]);max_loss=min(ordered)
    cost50=next((x for x in cost.get('scenarios',[]) if x.get('round_trip_bps')==50),{})
    stressed_mean=cost50.get('mean_net_return')
    return {'status':'PASS' if len(net)>=MIN_FORWARD_N else 'PENDING_SAMPLE','n':len(net),
            'stress_type':'OBSERVED_DISTRIBUTION_PLUS_COST_SENSITIVITY','worst_decile_mean':worst_decile,
            'max_observed_loss':max_loss,'mean_at_50bps_round_trip':stressed_mean,
            'historical_crash_replay_claimed':False,'synthetic_market_path_claimed':False,
            'can_change_live_risk':False,'real_trading':False}


def manual_promotion_gate(tasks, prior_16_40=None):
    prior=(prior_16_40 or {}).get('tasks') or {}
    required_current=('41','44','46','48','50','53','54','55','56','57','58')
    current={k:(tasks.get(k) or {}).get('state') for k in required_current}
    prior_required={'20':(prior.get('20') or {}).get('state'),
                    '36':(prior.get('36') or {}).get('state'),
                    '37':(prior.get('37') or {}).get('state'),
                    '38':(prior.get('38') or {}).get('state')}
    acceptable={'PASS','READY_FOR_MANUAL_COMPARISON'}
    blockers=[f'task_{k}:{v}' for k,v in current.items() if v not in acceptable]
    blockers += [f'prior_task_{k}:{v}' for k,v in prior_required.items() if v!='PASS']
    eligible=not blockers
    return {'status':'MANUAL_REVIEW_ELIGIBLE' if eligible else 'BLOCKED_EVIDENCE',
            'required_tasks':current,'required_prior_tasks':prior_required,'blockers':blockers,
            'manual_review_only':True,'automatic_promotion':False,'automatic_demotion':False,
            'automatic_release':False,'setup_1_6_allowed':False,'live_execution_allowed':False,
            'real_trading':False}


def dashboard_v3(tasks, prior_16_40=None, ranking=None, stress=None, promotion=None):
    states={}
    for k,v in tasks.items():states[str(v.get('state'))]=states.get(str(v.get('state')),0)+1
    prior_tasks=(prior_16_40 or {}).get('tasks') or {}
    combined={str(k):(v or {}).get('state') for k,v in prior_tasks.items() if str(k).isdigit()}
    combined.update({str(k):(v or {}).get('state') for k,v in tasks.items()})
    blockers=list((promotion or {}).get('blockers') or [])
    return {'dashboard_contract':'AUTONOMOUS_SIMULATOR_V3','learning_scope':'PRIORITIES_16_60',
            'tasks_41_60_state_counts':states,'combined_task_states':combined,
            'promotion_status':(promotion or {}).get('status'),'promotion_blockers':blockers,
            'top3':(ranking or {}).get('top3') or [],'stress':stress or {},
            'banner':'SIMULATION ONLY — NO REAL MONEY','automatic_promotion':False,
            'automatic_release':False,'live_execution_allowed':False,'real_trading':False}


def build_priorities_41_60(rows=None, analytics=None, competition=None, prior_16_40=None, *, persist=False):
    rows=list(rows or [])
    analytics=analytics or {}
    competition=competition or competition_snapshot(rows,{})
    cal=calibration_quality(rows,analytics);drift=calibration_drift_guard(rows,analytics)
    confidence=confidence_uncertainty_guard(rows);abst=abstention_quality_guard(rows,analytics)
    tail=downside_tail_risk(rows);cost=cost_sensitivity(rows);benchmark=benchmark_robustness(rows)
    decay=decay_guard(rows,analytics);ranking=ranking_guard(rows,analytics)
    cc=_competition_piece(competition,'champion_challenger')
    degradation=_competition_piece(competition,'champion_degradation')
    ensemble=_competition_piece(competition,'shadow_ensemble')
    diversity_reward=_competition_piece(competition,'diversity_reward')
    routing=_competition_piece(competition,'dynamic_routing')
    meta=_competition_piece(competition,'meta_learning')
    transfer=_competition_piece(competition,'historical_live_transfer')
    diversity=((prior_16_40 or {}).get('diversity') or {})
    anti=anti_overfit_diagnostic(rows,cal,routing,transfer,diversity,prior_16_40)
    stress=empirical_stress(rows,cost)
    tasks={
      '41':{'state':cal.get('status','PENDING_SAMPLE'),'evidence':cal},
      '42':{'state':drift.get('status','PENDING_SAMPLE'),'evidence':drift},
      '43':{'state':confidence.get('status','PENDING_SAMPLE'),'evidence':confidence},
      '44':{'state':abst.get('status','PENDING_SAMPLE'),'evidence':abst},
      '45':{'state':tail.get('status','PENDING_SAMPLE'),'evidence':tail},
      '46':{'state':cost.get('status','PENDING_SAMPLE'),'evidence':cost},
      '47':{'state':benchmark.get('status','PENDING_SAMPLE'),'evidence':benchmark},
      '48':{'state':decay.get('status','PENDING_SAMPLE'),'evidence':decay},
      '49':{'state':ranking.get('status','PENDING_SAMPLE'),'evidence':ranking},
      '50':{'state':cc.get('status','PENDING_SAMPLE'),'evidence':cc},
      '51':{'state':degradation.get('status','PENDING_SAMPLE'),'evidence':degradation},
      '52':{'state':ensemble.get('status','PENDING_SAMPLE'),'evidence':ensemble},
      '53':{'state':diversity_reward.get('status','PENDING_SAMPLE'),'evidence':diversity_reward},
      '54':{'state':routing.get('status','PENDING_SAMPLE'),'evidence':routing},
      '55':{'state':meta.get('status','PENDING_SAMPLE'),'evidence':meta},
      '56':{'state':transfer.get('status','PENDING_SAMPLE'),'evidence':transfer},
      '57':{'state':anti.get('status','PENDING_SAMPLE'),'evidence':anti},
      '58':{'state':stress.get('status','PENDING_SAMPLE'),'evidence':stress},
    }
    promotion=manual_promotion_gate(tasks,prior_16_40)
    tasks['59']={'state':promotion['status'],'evidence':promotion}
    dash=dashboard_v3(tasks,prior_16_40,ranking,stress,promotion)
    tasks['60']={'state':'PASS','evidence':dash}
    source=max((str(r.get('evaluated_at')) for r in rows if r.get('evaluated_at')),default=None)
    payload={'status':'AUTONOMOUS_PAPER_LEARNING_41_60','observed_at':datetime.now(timezone.utc).isoformat(),
             'tasks':tasks,'calibration':cal,'calibration_drift':drift,'confidence_uncertainty':confidence,
             'abstention_quality':abst,'downside_tail_risk':tail,'cost_sensitivity':cost,
             'benchmark_robustness':benchmark,'signal_decay':decay,'ranking_369':ranking,
             'champion_challenger':cc,'champion_degradation':degradation,'shadow_ensemble':ensemble,
             'diversity_reward':diversity_reward,'dynamic_routing':routing,'meta_learning':meta,
             'historical_live_transfer':transfer,'anti_overfit':anti,'empirical_stress':stress,
             'manual_promotion_gate':promotion,'dashboard_v3':dash,'source_max_evaluated_at':source,
             'automatic_promotion':False,'automatic_demotion':False,'automatic_release':False,
             'setup_1_6_allowed':False,'live_execution_allowed':False,'simulation_only':True,'real_trading':False}
    if persist and persistence.enabled():
        try:
            s=persistence.put_snapshot(SNAPSHOT_KIND,payload,source_max_evaluated_at=source)
            combined={'status':'AUTONOMOUS_PAPER_LEARNING_16_60','priorities_16_40':prior_16_40 or {},
                      'priorities_41_60':payload,'dashboard_v3':dash,'automatic_promotion':False,
                      'live_execution_allowed':False,'real_trading':False}
            c=persistence.put_snapshot(COMBINED_KIND,combined,source_max_evaluated_at=source)
            payload['persistence']={'status':'PERSISTED','snapshot_id':s.get('id'),'combined_id':c.get('id'),'real_trading':False}
        except Exception as exc:
            payload['persistence']={'status':'DEGRADED','error':f'{type(exc).__name__}: {str(exc)[:300]}','real_trading':False}
    else:
        payload['persistence']={'status':'NOT_REQUESTED' if not persist else 'NOT_CONFIGURED','real_trading':False}
    return payload
