"""Radar autonomous handoff for focusing human development effort on CEO de IAs.

This module does not create a second simulator, trade, promote models, or accelerate
forward evidence. It turns the existing PAPER runtime into a low-maintenance service:
continuous memory health, prospective data-contract checks, shadow-policy experiments,
horizon watches, an executive summary, and an explicit MAINTENANCE_ONLY freeze state.
"""
from __future__ import annotations

import math
import time
from datetime import datetime, timezone
from typing import Any

import radar_autonomous_simulator_v1 as simulator
import radar_autonomous_paper_control_v1 as control
import radar_brain_persistence_v1 as persistence
from radar_forward_evidence_v2 import canonical_forward_rows

REAL_TRADING=False
SNAPSHOT_KIND='radar_ceo_handoff_v1'
MEMORY_HEALTH_KIND='radar_memory_health_v1'
DATA_CONTRACT='DECISION_MEMORY_V1'
REQUIRED_PROSPECTIVE_FIELDS=('symbol','model_version','family','regime','confidence','sector','industry','uncertainty','intended_horizon')


def _finite(v):
    try:
        x=float(v);return x if math.isfinite(x) else None
    except Exception:return None


def _parse(v):
    if not v:return None
    try:
        d=datetime.fromisoformat(str(v).replace('Z','+00:00'));return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:return None


def _age_seconds(v):
    d=_parse(v)
    return max(0.0,(datetime.now(timezone.utc)-d).total_seconds()) if d else None


def memory_health(sim_state:dict[str,Any],control_state:dict[str,Any],rows:list[dict[str,Any]]):
    age=_age_seconds(sim_state.get('last_cycle_at'))
    checkpoint_epoch=_finite(control_state.get('last_checkpoint_epoch'))
    checkpoint_age=max(0.0,time.time()-checkpoint_epoch) if checkpoint_epoch is not None else None
    threads=control_state.get('threads') or {}
    checks={
        'simulator_active':sim_state.get('active') is True,
        'paper_enabled':bool((sim_state.get('paper') or {}).get('enabled')),
        'cycle_fresh':age is not None and age<=3600,
        'checkpoint_fresh':checkpoint_age is not None and checkpoint_age<=1200,
        'control_thread_alive':threads.get('control') is True,
        'supervisor_thread_alive':threads.get('supervisor') is True,
        'persistence_enabled':bool((control_state.get('persistence') or {}).get('enabled')),
        'forward_memory_present':len(rows)>0,
    }
    blockers=[k for k,v in checks.items() if not v]
    return {'status':'PASS' if not blockers else 'ATTENTION','checks':checks,'blockers':blockers,
            'last_cycle_at':sim_state.get('last_cycle_at'),'last_cycle_age_seconds':age,
            'checkpoint_age_seconds':checkpoint_age,'forward_rows':len(rows),
            'completed_cycles':sim_state.get('completed_cycles'),'completed_experiments':sim_state.get('completed_experiments'),
            'memory_is_continuous':not blockers,'real_trading':False}


def _field_value(row,key):
    payload=row.get('payload') or {}
    if key=='symbol':return row.get('symbol') or payload.get('asset') or payload.get('symbol')
    if key=='model_version':return row.get('model_version') or payload.get('model_version')
    if key=='family':return payload.get('family') or payload.get('strategy_family') or row.get('family')
    if key=='regime':return row.get('regime') or payload.get('regime') or (payload.get('uncertainty') or {}).get('regime')
    if key=='confidence':return row.get('confidence') if row.get('confidence') is not None else payload.get('confidence')
    if key=='sector':return row.get('sector') or payload.get('sector') or (payload.get('metadata') or {}).get('sector')
    if key=='industry':return row.get('industry') or payload.get('industry') or (payload.get('metadata') or {}).get('industry')
    if key=='uncertainty':return row.get('uncertainty') or payload.get('uncertainty')
    if key=='intended_horizon':return row.get('intended_horizon') or payload.get('intended_horizon')
    return row.get(key)


def data_completeness(rows:list[dict[str,Any]]):
    recent=list(rows[-200:])
    def present(r,key):
        value=_field_value(r,key)
        if key=='uncertainty':return value not in (None,'',{})
        return value not in (None,'','UNKNOWN')
    counts={k:sum(1 for r in recent if present(r,k)) for k in REQUIRED_PROSPECTIVE_FIELDS}
    ratios={k:(v/len(recent) if recent else 0.0) for k,v in counts.items()}
    holes=[k for k,v in ratios.items() if v<0.95]
    matured=[r for r in recent if r.get('matured') is True]
    duration_n=sum(1 for r in matured if isinstance(r.get('outcome'),dict) and r['outcome'].get('observation_holding_seconds') is not None)
    duration_ratio=duration_n/len(matured) if matured else None
    current_contract_n=sum(1 for r in recent if (r.get('payload') or {}).get('decision_memory_contract')==DATA_CONTRACT)
    return {'status':'PASS' if recent and not holes else 'ATTENTION','contract':DATA_CONTRACT,
            'sample_n':len(recent),'current_contract_n':current_contract_n,'coverage':ratios,'holes':holes,
            'matured_recent_n':len(matured),'prospective_observation_duration_n':duration_n,
            'prospective_observation_duration_ratio':duration_ratio,
            'prospective_capture_required':list(REQUIRED_PROSPECTIVE_FIELDS),
            'retroactive_fill_forbidden':True,'missing_data_must_remain_explicit':True,
            'legacy_rows_do_not_block_new_contract_capture':True,
            'holding_duration_requires_execution_outcome_not_prediction_age':True,
            'observation_duration_is_not_execution_duration':True,'real_trading':False}


def shadow_brain_registry(sim_state:dict[str,Any],rows:list[dict[str,Any]]):
    ex=list(sim_state.get('recent_experiments') or [])
    configs=[];seen=set()
    for e in ex:
        cfg=e.get('configuration') or {}
        fp=str(sorted(cfg.items()))
        if fp in seen:continue
        seen.add(fp);configs.append({'experiment_id':e.get('experiment_id'),'generation':e.get('generation'),
                                     'stage':e.get('stage'),'gate_status':e.get('gate_status'),'configuration':cfg})
    models=sorted({str(r.get('model_version')) for r in rows if r.get('model_version') not in (None,'','UNKNOWN')})
    return {'status':'PASS' if len(configs)>=2 else 'PENDING_SAMPLE','distinct_shadow_configurations':len(configs),
            'shadow_candidates':configs[:10],'forward_model_versions':models,'forward_model_count':len(models),
            'multi_model_forward_evidence_status':'PASS' if len(models)>=2 else 'PENDING_SAMPLE',
            'paper_shadow_only':True,'automatic_champion_replacement':False,'real_trading':False}


def threshold_experiment(rows:list[dict[str,Any]]):
    matured=[r for r in rows if r.get('matured') is True and r.get('natural') is True and str(r.get('decision_state') or '').upper() in {'BUY','SELL'}]
    variants=[]
    for t in (0.50,0.55):
        xs=[]
        for r in matured:
            c=_finite(r.get('confidence'));ret=_finite(r.get('net_return'))
            if c is not None and ret is not None and c>=t:xs.append(ret)
        variants.append({'threshold':t,'n':len(xs),'mean_net_return':sum(xs)/len(xs) if xs else None,
                         'sample_gate':len(xs)>=20})
    return {'status':'ACTIVE','experiment':'ENTRY_THRESHOLD_050_VS_055','variants':variants,
            'prospective_shadow_recording':True,'changes_execution_policy':False,
            'automatic_strategy_change':False,'real_trading':False}


def horizon_watch(learning_16_40:dict[str,Any]):
    tasks=learning_16_40.get('tasks') or {}
    out={}
    for horizon,task in (('1w','36'),('1m','37'),('3m','38')):
        row=tasks.get(task) or {};out[horizon]={'state':row.get('state'),'evidence':row.get('evidence') or {}}
    return {'status':'PASS' if all((x.get('state')=='PASS' for x in out.values())) else 'PENDING_TIME_OR_SAMPLE',
            'horizons':out,'automatic_evaluation':True,'backfill_allowed':False,'acceleration_allowed':False,'real_trading':False}


def executive_summary(sim_state,control_state,learning_16_40,learning_41_60,rows):
    paper=sim_state.get('paper') or {};t16=learning_16_40.get('tasks') or {};t41=learning_41_60.get('tasks') or {}
    return {'status':'AUTONOMOUS_PAPER_LEARNING','banner':'SIMULATION ONLY — NO REAL MONEY',
            'simulator_active':sim_state.get('active') is True,'watchdog':control.watchdog_status(),
            'completed_cycles':sim_state.get('completed_cycles'),'completed_experiments':sim_state.get('completed_experiments'),
            'last_cycle_at':sim_state.get('last_cycle_at'),'paper_total':paper.get('total'),'paper_cash':paper.get('cash'),
            'paper_pnl_pct':paper.get('pnl_pct'),'forward_rows':len(rows),
            'net_alpha_state':(t16.get('20') or {}).get('state'),'calibration_state':(t41.get('41') or {}).get('state'),
            'abstention_state':(t41.get('44') or {}).get('state'),'brain_promotion_state':(t41.get('59') or {}).get('state'),
            'horizons':horizon_watch(learning_16_40).get('horizons'),
            'human_attention_policy':'ONLY_OPERATIONAL_FAILURE_OR_MEANINGFUL_EVIDENCE_MILESTONE',
            'development_mode':'MAINTENANCE_ONLY','primary_human_project':'CEO_DE_IAS',
            'automatic_promotion':False,'live_execution_allowed':False,'real_trading':False}


def build_handoff(rows=None,sim_state=None,control_state=None,learning_16_40=None,learning_41_60=None,*,persist=False):
    rows=list(rows if rows is not None else canonical_forward_rows())
    sim_state=dict(sim_state if sim_state is not None else simulator.simulator_status())
    control_state=dict(control_state if control_state is not None else control.control_status())
    learning_16_40=dict(learning_16_40 or {})
    learning_41_60=dict(learning_41_60 or {})
    mem=memory_health(sim_state,control_state,rows);data=data_completeness(rows);brains=shadow_brain_registry(sim_state,rows)
    exp=threshold_experiment(rows);horiz=horizon_watch(learning_16_40)
    supervisor_ok=mem['checks'].get('control_thread_alive') and mem['checks'].get('supervisor_thread_alive')
    tasks={
      '1':{'priority':'SIMULATOR_PAPER_24_7','state':'PASS' if mem['checks'].get('simulator_active') and mem['checks'].get('cycle_fresh') else 'ATTENTION','evidence':mem},
      '2':{'priority':'CONTINUOUS_MEMORY','state':mem['status'],'evidence':mem},
      '3':{'priority':'DATA_MEMORY_ANALYSIS_LEARNING_LOOP','state':'PASS' if len(rows)>0 and int(sim_state.get('completed_experiments') or 0)>0 else 'PENDING_SAMPLE','evidence':{'forward_rows':len(rows),'completed_experiments':sim_state.get('completed_experiments'),'brain_snapshots_expected':True,'real_trading':False}},
      '4':{'priority':'LOW_MAINTENANCE_SUPERVISOR','state':'PASS' if supervisor_ok else 'ATTENTION','evidence':{'threads':control_state.get('threads'),'watchdog':control.watchdog_status(),'autorestart_control_thread':True,'real_trading':False}},
      '5':{'priority':'PROSPECTIVE_DATA_COMPLETENESS','state':data['status'],'evidence':data},
      '6':{'priority':'DISTINCT_SHADOW_BRAINS','state':brains['status'],'evidence':brains},
      '7':{'priority':'NET_ALPHA_SHADOW_EXPERIMENTS','state':'ACTIVE','evidence':exp},
      '8':{'priority':'NATURAL_MULTI_HORIZON_MATURITY','state':horiz['status'],'evidence':horiz},
      '9':{'priority':'EXECUTIVE_SUMMARY','state':'PASS','evidence':{'endpoint':'/autonomous-simulator/executive-v1','daily_weekly_reports':True,'real_trading':False}},
      '10':{'priority':'FREEZE_RADAR_FEATURE_DEVELOPMENT','state':'PASS','evidence':{'development_mode':'MAINTENANCE_ONLY','allowed_changes':['OPERABILITY_FIX','DATA_INTEGRITY_FIX','EVIDENCE_DRIVEN_CHANGE','SECURITY_FIX'],'feature_expansion':False,'primary_human_project':'CEO_DE_IAS','real_trading':False}},
    }
    out={'status':'RADAR_AUTONOMOUS_HANDOFF','observed_at':datetime.now(timezone.utc).isoformat(),'tasks':tasks,
         'executive':executive_summary(sim_state,control_state,learning_16_40,learning_41_60,rows),
         'development_mode':'MAINTENANCE_ONLY','primary_human_project':'CEO_DE_IAS',
         'simulation_only':True,'automatic_promotion':False,'automatic_release':False,'live_execution_allowed':False,'real_trading':False}
    if persist and persistence.enabled():
        try:
            source=max((str(r.get('evaluated_at')) for r in rows if r.get('evaluated_at')),default=None)
            persistence.put_snapshot(SNAPSHOT_KIND,out,source_max_evaluated_at=source)
            persistence.put_snapshot(MEMORY_HEALTH_KIND,mem,source_max_evaluated_at=source)
        except Exception as exc:out['persistence_error']=f'{type(exc).__name__}: {str(exc)[:400]}'
    return out
