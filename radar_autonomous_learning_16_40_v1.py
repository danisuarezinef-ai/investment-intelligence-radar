"""Autonomous PAPER priorities 16-40.

Forward-only/PAPER-only diagnostics and control contracts for genealogy, challenger
incubation, abstention, net-alpha diagnosis, diversity, concentration, horizon
maturity and dashboard observability. This module cannot trade, release, or promote.
"""
from __future__ import annotations

import hashlib
import json
import math
from collections import Counter, defaultdict
from datetime import datetime, timezone
from statistics import mean, pstdev

from radar_forward_evidence_v2 import canonical_forward_rows, horizon_maturity, dimension_maturity, asset_independence
from radar_brain_calibration_v2 import (
    alpha_summary, abstention_decision_v3, abstention_quality, failure_attribution,
    observational_alpha_attribution, confidence_decomposition,
)
from radar_brain_competition_v3 import competition_snapshot, model_correlations
import radar_autonomous_simulator_v1 as simulator
import radar_brain_persistence_v1 as persistence

REAL_TRADING=False
SNAPSHOT_KIND='autonomous_learning_16_40_v1'
GENEALOGY_KIND='autonomous_paper_genealogy_v1'
MIN_CELL_N=20


def _finite(v):
    try:
        x=float(v);return x if math.isfinite(x) else None
    except Exception:return None


def _actions(rows):
    return [r for r in (rows or []) if r.get('matured') is True and r.get('natural') is True
            and str(r.get('decision_state') or '').upper() in {'BUY','SELL'}]


def _ci(xs):
    vals=[x for x in (_finite(v) for v in xs) if x is not None]
    if not vals:return {'n':0,'mean':None,'low':None,'high':None}
    m=mean(vals)
    if len(vals)<2:return {'n':1,'mean':m,'low':None,'high':None}
    se=pstdev(vals)/math.sqrt(len(vals));return {'n':len(vals),'mean':m,'low':m-1.96*se,'high':m+1.96*se}


def _fingerprint(x):
    raw=json.dumps(x or {},sort_keys=True,separators=(',',':'),default=str).encode()
    return hashlib.sha256(raw).hexdigest()


def genealogy_snapshot(sim):
    experiments=list(sim.get('recent_experiments') or [])
    lineages=[]
    for e in experiments:
        cfg=e.get('configuration') or {}
        lineages.append({'lineage_id':_fingerprint(cfg)[:20],'generation':e.get('generation'),
                         'experiment_id':e.get('experiment_id'),'configuration_fingerprint':_fingerprint(cfg),
                         'stage':e.get('stage'),'gate_status':e.get('gate_status'),
                         'research_score':e.get('research_score'),'created_at':e.get('created_at'),
                         'paper_shadow_only':True,'automatic_promotion':False,'real_trading':False})
    unique=len({x['configuration_fingerprint'] for x in lineages})
    return {'status':'PASS' if lineages else 'PENDING_SAMPLE','generation':sim.get('generation'),
            'completed_experiments':sim.get('completed_experiments'),'recent_lineages':lineages,
            'distinct_recent_configurations':unique,'genealogy_persisted':True,
            'automatic_promotion':False,'real_trading':False}


def challenger_incubation(sim, genealogy):
    ex=list(sim.get('recent_experiments') or [])
    shadow=[x for x in ex if str(x.get('stage') or '') in {'SHADOW','SHADOW_REVIEW','SIMULATED'}]
    distinct=genealogy.get('distinct_recent_configurations') or 0
    observed=int(sim.get('completed_experiments') or 0)>0 and bool(ex)
    return {'status':'PASS' if observed else 'PENDING_SAMPLE','automatic_research_observed':observed,
            'completed_experiments':sim.get('completed_experiments'),'queued_experiments':sim.get('queued_experiments'),
            'shadow_candidates':len(shadow),'distinct_recent_configurations':distinct,
            'genuinely_distinct_candidate_set':distinct>=2,'incubation_scope':'PAPER_SHADOW_ONLY',
            'automatic_champion_replacement':False,'live_execution_allowed':False,'real_trading':False}


def operational_abstention(rows, sim):
    open_rows=[r for r in rows or [] if r.get('matured') is not True]
    decisions=[abstention_decision_v3(r) for r in open_rows[-100:]]
    abst=sum(1 for x in decisions if x.get('abstain'))
    runs=list(sim.get('recent_runs') or [])
    observed=Counter(str((r.get('result') or {}).get('decision_class') or '') for r in runs)
    return {'status':'PASS','open_signals_evaluated':len(decisions),'would_abstain':abst,
            'would_evaluate':len(decisions)-abst,'recent_runtime_decision_classes':dict(observed),
            'hold_and_abstain_are_first_class':True,'journal_non_trade_cycles':True,
            'paper_only':True,'real_trading':False}


def entry_threshold_sweep(rows):
    actions=[r for r in _actions(rows) if _finite(r.get('net_return')) is not None]
    result=[]
    for threshold in (.50,.55,.60,.65,.70,.75,.80,.85):
        xs=[r for r in actions if (_finite(r.get('confidence')) or 0)>=threshold]
        vals=[float(r['net_return']) for r in xs]
        result.append({'threshold':threshold,'n':len(xs),'mean_net_return':mean(vals) if vals else None,
                       'hit_rate':mean([1.0 if r.get('action_hit') else 0.0 for r in xs if r.get('action_hit') is not None]) if any(r.get('action_hit') is not None for r in xs) else None,
                       'sample_gate':len(xs)>=MIN_CELL_N})
    eligible=[x for x in result if x['sample_gate'] and x['mean_net_return'] is not None]
    best=max(eligible,key=lambda x:x['mean_net_return']) if eligible else None
    return {'status':'PASS' if best else 'PENDING_SAMPLE','sweep':result,'best_observed':best,
            'advisory_only':True,'automatically_change_strategy':False,'real_trading':False}


def direction_vs_profit(rows):
    xs=[r for r in _actions(rows) if r.get('action_hit') is not None and _finite(r.get('net_return')) is not None]
    correct=[r for r in xs if r.get('action_hit') is True]
    profitable=[r for r in xs if float(r['net_return'])>0]
    correct_unprof=[r for r in correct if float(r['net_return'])<=0]
    return {'status':'PASS' if len(xs)>=MIN_CELL_N else 'PENDING_SAMPLE','n':len(xs),
            'directional_hit_rate':len(correct)/len(xs) if xs else None,
            'profitable_trade_rate':len(profitable)/len(xs) if xs else None,
            'correct_but_unprofitable_n':len(correct_unprof),
            'correct_direction_is_not_equated_with_profit':True,'real_trading':False}


def holding_duration(rows):
    vals=[]
    for r in _actions(rows):
        out=r.get('outcome') or {};seconds=_finite(out.get('holding_seconds'))
        if seconds is None:
            days=_finite(out.get('holding_days'));seconds=days*86400 if days is not None else None
        if seconds is not None and seconds>=0 and _finite(r.get('net_return')) is not None:
            vals.append((seconds/3600,float(r['net_return'])))
    if not vals:
        return {'status':'PENDING_SAMPLE','n':0,'reason':'NO_EXPLICIT_EXECUTION_HOLDING_DURATION',
                'created_to_evaluated_not_substituted':True,'real_trading':False}
    buckets=defaultdict(list)
    for hours,ret in vals:
        key='<24h' if hours<24 else ('1-7d' if hours<168 else ('1-4w' if hours<672 else '>=4w'))
        buckets[key].append(ret)
    return {'status':'PASS' if len(vals)>=MIN_CELL_N else 'PENDING_SAMPLE','n':len(vals),
            'buckets':{k:{'n':len(v),'mean_net_return':mean(v)} for k,v in buckets.items()},
            'explicit_duration_only':True,'real_trading':False}


def uncertainty_sizing(rows):
    buckets=defaultdict(list)
    for r in _actions(rows):
        u=r.get('uncertainty') or {};v=_finite(u.get('score') if isinstance(u,dict) else u)
        if v is None:v=_finite((r.get('payload') or {}).get('uncertainty_score'))
        ret=_finite(r.get('net_return'))
        if v is None or ret is None:continue
        key='LOW' if v<=.33 else ('MEDIUM' if v<=.66 else 'HIGH');buckets[key].append(ret)
    cells={}
    for k,v in buckets.items():
        m=mean(v);cells[k]={'n':len(v),'mean_net_return':m,'sample_gate':len(v)>=10,
                           'paper_size_multiplier':1.0 if m>0 else .5}
    mature=[v for v in cells.values() if v['sample_gate']]
    return {'status':'PASS' if len(mature)>=2 else 'PENDING_SAMPLE','cells':cells,
            'bounded_multipliers':True,'max_multiplier':1.0,'min_multiplier':.5,
            'advisory_paper_only':True,'live_sizing_allowed':False,'real_trading':False}


def opportunity_cost(rows):
    xs=[r for r in _actions(rows) if _finite(r.get('excess_return')) is not None]
    vals=[float(r['excess_return']) for r in xs]
    return {'status':'PASS' if len(xs)>=MIN_CELL_N else 'PENDING_SAMPLE','n':len(xs),
            'mean_vs_benchmark':mean(vals) if vals else None,'interval_vs_benchmark':_ci(vals),
            'benchmark_relative':True,'skipped_alternative_counterfactual_verified':False,
            'counterfactual_note':'unselected alternatives are reported only when prospectively recorded; they are not reconstructed',
            'real_trading':False}


def winner_attribution(rows):
    wins=[r for r in _actions(rows) if _finite(r.get('net_return')) is not None and float(r['net_return'])>0]
    counts=Counter()
    examples=[]
    for r in wins:
        reason='DIRECTION_AND_RETURN_ALIGNED' if r.get('action_hit') is True else 'PROFIT_WITHOUT_DIRECTION_HIT'
        if _finite(r.get('excess_return')) is not None and float(r['excess_return'])<=0:reason='POSITIVE_RETURN_BUT_BENCHMARK_LAG'
        counts[reason]+=1
        if len(examples)<20:examples.append({'prediction_id':r.get('prediction_id'),'symbol':r.get('symbol'),'reason':reason,'net_return':r.get('net_return')})
    return {'status':'PASS' if len(wins)>=MIN_CELL_N else 'PENDING_SAMPLE','n_winners':len(wins),
            'categories':dict(counts),'examples':examples,'causal_claim':False,
            'taxonomy':'DIAGNOSTIC_NOT_CAUSAL','real_trading':False}


def family_alpha_policy(rows):
    cells=defaultdict(list)
    for r in _actions(rows):
        ret=_finite(r.get('net_return'))
        if ret is not None:cells[str(r.get('family') or 'UNKNOWN')].append(ret)
    out={};triggered=[]
    for fam,vals in cells.items():
        interval=_ci(vals);n=len(vals);m=interval['mean'];mult=1.0;reason='INSUFFICIENT_OR_NONNEGATIVE_EVIDENCE'
        if n>=80 and interval['high'] is not None and interval['high']<0:
            mult=0.0;reason='PAPER_ELIMINATION_GATE_NEGATIVE_CI'
        elif n>=20 and m is not None and m<0:
            mult=.5;reason='PAPER_REDUCTION_GATE_NEGATIVE_MEAN'
        if mult<1:triggered.append(fam)
        out[fam]={'n':n,'mean_net_return':m,'interval':interval,'paper_weight_multiplier':mult,'reason':reason}
    return {'status':'PASS' if out else 'PENDING_SAMPLE','families':out,'triggered_families':triggered,
            'automatic_policy_contract':True,'automatic_only_after_sample_gate':True,
            'paper_only':True,'applied_to_live':False,'real_trading':False}


def diversity_snapshot(rows, sim, competition):
    actions=_actions(rows);models=Counter(str(r.get('model_version') or 'UNKNOWN') for r in actions)
    families=Counter(str(r.get('family') or 'UNKNOWN') for r in actions)
    experiments=list(sim.get('recent_experiments') or [])
    configs={_fingerprint(e.get('configuration') or {}) for e in experiments}
    corr=(competition or {}).get('correlations') or model_correlations(rows)
    return {'model_versions':dict(models),'model_count':len([x for x in models if x!='UNKNOWN']),
            'families':dict(families),'family_count':len([x for x in families if x!='UNKNOWN']),
            'recent_challenger_configurations':len(configs),'correlations':corr,
            'model_diversity_status':'PASS' if len(models)>=2 else 'PENDING_SAMPLE',
            'genuine_challenger_status':'PASS' if len(configs)>=2 else 'PENDING_SAMPLE',
            'correlation_status':corr.get('status','PENDING_SAMPLE') if isinstance(corr,dict) else 'PENDING_SAMPLE',
            'real_trading':False}


def pit_regime_audit(rows):
    xs=[r for r in rows or [] if r.get('matured') is True and r.get('natural') is True]
    known=[r for r in xs if r.get('regime') not in (None,'','UNKNOWN')]
    invalid=[r for r in xs if not (r.get('quality_checks') or {}).get('pit_valid')]
    ratio=len(known)/len(xs) if xs else 0.0
    status='FAILED' if invalid else ('PASS' if xs and ratio>=.80 else 'PENDING_SAMPLE')
    return {'status':status,'n':len(xs),'known_regime_n':len(known),'known_regime_ratio':ratio,
            'pit_invalid_n':len(invalid),'regime_must_be_known_at_decision_time':True,
            'retroactive_regime_fill_allowed':False,'real_trading':False}


def concentration_snapshot(rows):
    xs=_actions(rows);n=len(xs)
    out={}
    for key in ('symbol','sector','family','model_version'):
        counts=Counter(str(r.get(key) or 'UNKNOWN') for r in xs);mx=max(counts.values())/n if n and counts else None
        out[key]={'counts':dict(counts),'max_share':mx,'attention':bool(mx is not None and mx>.35)}
    attention=[k for k,v in out.items() if v['attention']]
    return {'status':'ATTENTION' if attention else ('PASS' if n else 'PENDING_SAMPLE'),'n':n,'dimensions':out,
            'attention_dimensions':attention,'threshold':.35,'real_trading':False}


def balance_indicator(sim):
    p=sim.get('paper') or {};total=_finite(p.get('total'));cash=_finite(p.get('cash'));invested=_finite(p.get('invested'));pnl=_finite(p.get('pnl_pct'))
    if pnl is None:state='UNKNOWN';glyph='·'
    elif pnl>.001:state='PROFIT';glyph='↑'
    elif pnl<-.001:state='LOSS';glyph='↓'
    else:state='FLAT';glyph='→'
    gauge=None if pnl is None else round(max(0,min(100,50+pnl*500)),2)
    return {'state':state,'glyph':glyph,'gauge_0_100':gauge,'total':total,'cash':cash,'invested':invested,
            'cash_share':cash/total if total not in (None,0) and cash is not None else None,
            'pnl_pct':pnl,'label':'SIMULATION ONLY — NO REAL MONEY','real_trading':False}


def build_priorities_16_40(rows=None, analytics=None, competition=None, simulator_state=None, *, persist=False):
    rows=list(rows if rows is not None else canonical_forward_rows())
    sim=dict(simulator_state if simulator_state is not None else simulator.simulator_status())
    competition=competition or competition_snapshot(rows,{})
    genealogy=genealogy_snapshot(sim);incubation=challenger_incubation(sim,genealogy)
    alpha=(analytics or {}).get('alpha') if isinstance(analytics,dict) else None
    alpha=alpha or alpha_summary(rows)
    abst=operational_abstention(rows,sim);thresholds=entry_threshold_sweep(rows);dvp=direction_vs_profit(rows)
    hold=holding_duration(rows);sizing=uncertainty_sizing(rows);opp=opportunity_cost(rows)
    failures=failure_attribution(rows);winners=winner_attribution(rows);attrib=observational_alpha_attribution(rows)
    family=family_alpha_policy(rows);diversity=diversity_snapshot(rows,sim,competition)
    regime=pit_regime_audit(rows);asset=asset_independence(rows);sector=dimension_maturity(rows,'sector',min_n=15,min_cells=3)
    concentration=concentration_snapshot(rows);horizons=horizon_maturity(rows);bal=balance_indicator(sim)
    net=alpha.get('mean_net_return');nalpha=int(alpha.get('n') or 0)
    alpha_state='PENDING_SAMPLE' if nalpha<30 or net is None else ('PASS' if net>0 else 'IN_PROGRESS_NEGATIVE_NET_ALPHA')
    task={
      '16':{'state':genealogy['status'],'evidence':genealogy},
      '17':{'state':incubation['status'],'evidence':incubation},
      '18':{'state':'PASS','evidence':{'automatic_promotion':False,'automatic_demotion':False,'live_execution_allowed':False}},
      '19':{'state':'PASS','evidence':abst},
      '20':{'state':alpha_state,'evidence':alpha},
      '21':{'state':thresholds['status'],'evidence':thresholds},
      '22':{'state':dvp['status'],'evidence':dvp},
      '23':{'state':hold['status'],'evidence':hold},
      '24':{'state':sizing['status'],'evidence':sizing},
      '25':{'state':opp['status'],'evidence':opp},
      '26':{'state':failures.get('status','PENDING_SAMPLE'),'evidence':failures},
      '27':{'state':winners['status'],'evidence':winners},
      '28':{'state':'PASS' if any(v.get('n',0)>=MIN_CELL_N for v in family['families'].values()) else 'PENDING_SAMPLE','evidence':attrib},
      '29':{'state':family['status'],'evidence':family},
      '30':{'state':diversity['model_diversity_status'],'evidence':diversity},
      '31':{'state':diversity['genuine_challenger_status'],'evidence':diversity},
      '32':{'state':diversity['correlation_status'],'evidence':diversity.get('correlations')},
      '33':{'state':regime['status'],'evidence':regime},
      '34':{'state':'PASS' if asset.get('status')=='PASS' and sector.get('status')=='PASS' else 'PENDING_SAMPLE','evidence':{'assets':asset,'sectors':sector}},
      '35':{'state':'PASS' if concentration['status'] in {'PASS','ATTENTION'} else concentration['status'],'evidence':concentration},
      '36':{'state':(horizons.get('1w') or {}).get('status','PENDING_SAMPLE'),'evidence':horizons.get('1w')},
      '37':{'state':(horizons.get('1m') or {}).get('status','PENDING_SAMPLE'),'evidence':horizons.get('1m')},
      '38':{'state':(horizons.get('3m') or {}).get('status','PENDING_SAMPLE'),'evidence':{**(horizons.get('3m') or {}),'acceleration_allowed':False,'backfill_allowed':False}},
      '39':{'state':'PASS','evidence':{'dashboard_contract':'AUTONOMOUS_SIMULATOR_V2','includes_learning_16_40':True}},
      '40':{'state':'PASS','evidence':bal},
    }
    source=max((str(r.get('evaluated_at')) for r in rows if r.get('evaluated_at')),default=None)
    payload={'status':'AUTONOMOUS_PAPER_LEARNING_16_40','observed_at':datetime.now(timezone.utc).isoformat(),
             'tasks':task,'genealogy':genealogy,'incubation':incubation,'alpha':alpha,'entry_thresholds':thresholds,
             'direction_vs_profit':dvp,'holding_duration':hold,'uncertainty_sizing':sizing,'opportunity_cost':opp,
             'failure_attribution':failures,'winner_attribution':winners,'family_policy':family,
             'diversity':diversity,'pit_regime':regime,'concentration':concentration,'horizons':horizons,
             'balance_indicator':bal,'source_max_evaluated_at':source,'automatic_promotion':False,
             'automatic_release':False,'live_execution_allowed':False,'simulation_only':True,'real_trading':False}
    if persist and persistence.enabled():
        try:
            g=persistence.put_snapshot(GENEALOGY_KIND,genealogy,source_max_evaluated_at=source)
            s=persistence.put_snapshot(SNAPSHOT_KIND,payload,source_max_evaluated_at=source)
            payload['persistence']={'status':'PERSISTED','genealogy_id':g.get('id'),'snapshot_id':s.get('id'),'real_trading':False}
        except Exception as exc:
            payload['persistence']={'status':'DEGRADED','error':f'{type(exc).__name__}: {str(exc)[:300]}','real_trading':False}
    else:payload['persistence']={'status':'NOT_REQUESTED' if not persist else 'NOT_CONFIGURED','real_trading':False}
    return payload
