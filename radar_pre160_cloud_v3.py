"""Cloud orchestration for pre-1.6 tasks 93-110."""
from __future__ import annotations

from datetime import datetime, timezone

from radar_operational_pipeline_v1 import operational_pipeline
from radar_pre160_cloud_v2 import runtime_snapshot as runtime_snapshot_v2
from radar_pre160_evidence_persistence_v1 import evidence_authority_status,persist_evidence_snapshot
from radar_pre160_persistence_v1 import pre160_evaluation_status
from radar_pre160_runtime_v3 import build_evidence_snapshot
from radar_validation_runtime_v3 import validation_runtime_v3

REAL_TRADING=False


def evidence_snapshot_v3():
    base=runtime_snapshot_v2();durable=pre160_evaluation_status(365);operational=operational_pipeline();validation=validation_runtime_v3()
    try:authority=evidence_authority_status(90)
    except Exception as exc:authority={'status':'EVIDENCE_AUTHORITY_DEGRADED','daily':[],'contexts':[],'chain':[],'error':str(exc)[:500],'real_trading':False}
    snapshot=build_evidence_snapshot(base_runtime=base,durable_eval=durable,evidence_authority=authority,
                                     forward_records=operational.get('forward_records') or [],validation=validation)
    snapshot['authority_before_persist']={'status':authority.get('status'),'chain_integrity':authority.get('chain_integrity'),'chain_records':authority.get('chain_records')}
    snapshot['real_trading']=False;return snapshot


def persist_evidence_cycle():
    snapshot=evidence_snapshot_v3();result=persist_evidence_snapshot(snapshot)
    return {'status':result.get('status'),'observed_at':snapshot.get('observed_at'),'snapshot_hash':result.get('snapshot_hash'),
            'contexts':result.get('contexts'),'chain':result.get('chain'),'readiness_1_6':snapshot.get('readiness_1_6'),
            'setup_allowed':False,'automatic_release':False,'can_trade':False,'real_trading':False}


def evidence_authority_report(days=90):
    authority=evidence_authority_status(days);daily=list(authority.get('daily') or []);latest=daily[-1] if daily else None
    return {'status':authority.get('status'),'observed_at':datetime.now(timezone.utc).isoformat(),'latest_daily':latest,
            'daily_count':len(daily),'contexts_count':len(authority.get('contexts') or []),'chain_records':authority.get('chain_records',0),
            'chain_integrity':authority.get('chain_integrity'),'setup_allowed':False,'automatic_release':False,'can_trade':False,'real_trading':False}


def tasks_91_110_audit():
    try:snapshot=evidence_snapshot_v3()
    except Exception as exc:return {'status':'DEGRADED','error':str(exc)[:700],'tasks':{},'setup_allowed':False,'can_trade':False,'real_trading':False}
    authority=snapshot.get('authority_before_persist') or {};ready=snapshot.get('readiness_1_6') or {};contexts=snapshot.get('contexts_to_freeze') or []
    tasks={
      '91':'VERIFIED_PRODUCTION_BASE',
      '92':'BOUNDARY_VERIFIED_CLASSIFICATION_PENDING' if sum((x.get('closes') or 0) for x in (snapshot.get('sample_gates') or {}).values())==0 else 'OBSERVED_PROSPECTIVE_CLASSIFICATION',
      '93':'IMPLEMENTED_DURABLE_DAILY',
      '94':'IMPLEMENTED_EVIDENCE_PENDING' if any(x.get('status')!='MATURE' for x in (snapshot.get('sample_gates') or {}).values()) else 'MATURE',
      '95':'IMPLEMENTED_'+str((snapshot.get('calibration') or {}).get('status')),
      '96':'IMPLEMENTED_'+str((snapshot.get('multi_benchmark') or {}).get('status')),
      '97':'IMPLEMENTED_'+str((snapshot.get('cost_slippage') or {}).get('status')),
      '98':'IMPLEMENTED_'+str((snapshot.get('capital_efficiency') or {}).get('status')),
      '99':'IMPLEMENTED_PIT_FREEZE' if contexts else 'IMPLEMENTED_WAITING_NEW_TRADE',
      '100':'IMPLEMENTED_'+str((snapshot.get('regime_horizon') or {}).get('status')),
      '101':'IMPLEMENTED_'+str((snapshot.get('stress_readiness') or {}).get('status')),
      '102':'IMPLEMENTED_'+str((snapshot.get('anti_overfitting_v2') or {}).get('status')),
      '103':'IMPLEMENTED_'+str((snapshot.get('champion_challenger_transfer') or {}).get('status')),
      '104':'IMPLEMENTED_WATCH_ONLY',
      '105':'IMPLEMENTED_'+str((snapshot.get('provenance') or {}).get('status')),
      '106':'IMPLEMENTED_SERVER_HASH_CHAIN_'+str(authority.get('chain_integrity') or 'PENDING_FIRST_RECORD'),
      '107':'IMPLEMENTED_'+str((snapshot.get('freshness') or {}).get('status')),
      '108':'IMPLEMENTED_'+str(ready.get('status')),
      '109':'IMPLEMENTED_DURABLE_DAILY_AUDIT',
      '110':'IMPLEMENTED_PENDING_CI_PRODUCTION_HTTP',
    }
    return {'status':'PRE160_TASKS_91_110','tasks':tasks,'readiness_1_6':ready,'snapshot_hash':snapshot.get('snapshot_hash'),
            'setup_allowed':False,'automatic_release':False,'automatic_promotion':False,'automatic_demotion':False,'can_trade':False,'real_trading':False}
