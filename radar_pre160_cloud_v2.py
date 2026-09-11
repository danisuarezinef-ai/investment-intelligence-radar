"""Read-only Cloud surfaces for the pre-1.6 integration block.

No function here can mutate strategy roles or execute capital.  The eventual 1.6
freeze remains blocked until the original 1..70 evidence gates and runtime duration
are genuinely satisfied.
"""
from __future__ import annotations

from datetime import datetime,timezone
from pathlib import Path
import re

from radar_pre160_persistence_v1 import current_evaluations,pre160_evaluation_status
from radar_pre160_runtime_v2 import opportunities_369,evidence_maturity
from radar_simulator_league_v1 import league_status
from radar_operational_pipeline_v1 import operational_pipeline
from radar_validation_runtime_v3 import validation_runtime_v3
from radar_autonomous_simulator_v1 import simulator_status
from radar_mobile_contract_v2 import mobile_summary
from radar_release_freeze_v1 import freeze_gate

REAL_TRADING=False


def _task_states(path='PRE160_MASTER_WORK.md'):
    states={}
    try:text=Path(path).read_text(encoding='utf-8')
    except Exception:return states
    for line in text.splitlines():
        m=re.match(r'^\|(\d+)\|[^|]+\|([^|]+)\|',line)
        if m:states[m.group(1)]=m.group(2).strip()
    return states


def _latest_daily(durable):
    latest={}
    for row in (durable or {}).get('daily') or []:
        key=str(row.get('competitor_key') or '')
        if not key:continue
        previous=latest.get(key)
        if previous is None or str(row.get('observed_at') or '')>=str(previous.get('observed_at') or ''):latest[key]=row
    return latest


def integration_task_states(runtime):
    maturity=(runtime or {}).get('evidence_maturity') or {};scorecards=(runtime or {}).get('scorecards') or []
    capture=bool(maturity.get('capture_started_at'));authority=(runtime or {}).get('authority_status')=='PRE160_EVALUATION_AUTHORITY'
    mapped={str(i):'IMPLEMENTED' for i in range(71,91)}
    mapped['71']='VERIFIED_CODE_ONLY'
    mapped['72']='PENDING_EXACT_RAILWAY_DEPLOY'
    mapped['73']='VERIFIED_RUNTIME' if capture else 'PENDING_CAPTURE_BOUNDARY'
    mapped['74']='VERIFIED_RUNTIME' if scorecards else 'PENDING_RUNTIME_SCORECARDS'
    for i in range(75,83):mapped[str(i)]='IMPLEMENTED_EVIDENCE_PENDING'
    mapped['83']='IMPLEMENTED_PROSPECTIVE_ONLY'
    mapped['84']='IMPLEMENTED_CANDIDATE_ONLY'
    mapped['85']='IMPLEMENTED'
    mapped['86']='IMPLEMENTED'
    mapped['87']='IMPLEMENTED'
    mapped['88']='IMPLEMENTED'
    mapped['89']='IMPLEMENTED_PENDING_CI'
    mapped['90']='IMPLEMENTED_PENDING_CI'
    if authority and capture: mapped['73']='VERIFIED_RUNTIME'
    return mapped


def runtime_snapshot():
    durable=pre160_evaluation_status(365)
    league=league_status(90)
    operational=operational_pipeline()
    validation=validation_runtime_v3()
    scorecards=current_evaluations()
    maturity=evidence_maturity(durable)
    return {
        'status':'PRE160_RUNTIME_V2',
        'authority_status':durable.get('status'),
        'capture_started_at':durable.get('capture_started_at'),
        'evidence_maturity':maturity,
        'scorecards':scorecards,
        'latest_durable_daily':_latest_daily(durable),
        'champion_key':league.get('champion_key'),
        'champion_degradation_watch':next((x.get('champion_degradation') for x in scorecards if x.get('champion_degradation')),None),
        'opportunities_369':opportunities_369(operational),
        'forward_reference_count':len(operational.get('forward_records') or []),
        'paper_gate_evidence':validation.get('paper_gate_evidence') or {},
        'learning_lessons':durable.get('lessons') or [],
        'archive_candidates':durable.get('archive_candidates') or [],
        'backfilled':False,'automatic_promotion':False,'automatic_demotion':False,
        'can_trade':False,'real_trading':False,
    }


def readiness_snapshot(runtime=None):
    runtime=runtime or runtime_snapshot();maturity=runtime.get('evidence_maturity') or {}
    master=_task_states();
    # Preserve the literal evidence states from the master map. CODE_READY/EVIDENCE are not silently promoted to VERIFIED.
    freeze=freeze_gate(master,{'status':'BLOCKED'},required_runtime_days=30,
                       observed_runtime_days=int(maturity.get('observed_runtime_days') or 0))
    integration=integration_task_states(runtime)
    blockers=list(freeze.get('blockers') or [])
    if runtime.get('authority_status')!='PRE160_EVALUATION_AUTHORITY':blockers.append('PRE160_AUTHORITY_NOT_READY')
    if not maturity.get('capture_started_at'):blockers.append('CAPTURE_BOUNDARY_NOT_STARTED')
    if int(maturity.get('prospective_closed_decisions') or 0)<8:blockers.append('PROSPECTIVE_CLOSED_SAMPLE_SMALL')
    return {'status':'PRE160_ACCUMULATING' if maturity.get('capture_started_at') else 'PRE160_NOT_STARTED',
            'integration_tasks_71_90':integration,'master_freeze':freeze,
            'blockers':list(dict.fromkeys(blockers)),'setup_allowed':False,
            'candidate_version':None,'automatic_promotion':False,'can_trade':False,'real_trading':False}


def mobile_runtime_summary(runtime=None):
    runtime=runtime or runtime_snapshot();league=league_status(90);sim=simulator_status()
    scores=[x.get('data_quality_score') for x in runtime.get('scorecards') or [] if x.get('data_quality_score') is not None]
    dq={'score':sum(float(x) for x in scores)/len(scores),'status':'AVAILABLE'} if scores else {'score':None,'status':'INSUFFICIENT_EVIDENCE'}
    payload=mobile_summary(league=league,simulator=sim,data_quality=dq,cloud={'status':sim.get('status')})
    readiness=readiness_snapshot(runtime)
    blockers=[]
    for row in runtime.get('scorecards') or []:
        p=row.get('promotion_v2') or {}
        if str(row.get('competitor_key'))!=str(runtime.get('champion_key')) and p.get('evidence_blockers'):
            blockers.append({'competitor_key':row.get('competitor_key'),'blockers':p.get('evidence_blockers')})
    payload.update({'evidence_maturity':runtime.get('evidence_maturity'),'promotion_blockers':blockers[:5],
                    'pre160_status':readiness.get('status'),'freeze_blockers':readiness.get('blockers'),
                    'setup_allowed':False,'can_trade':False,'real_trading':False})
    return payload
