"""Cloud orchestration for pre-1.6 tasks 111-130."""
from __future__ import annotations
from datetime import datetime,timezone

from radar_operational_pipeline_v1 import operational_pipeline
from radar_pre160_cloud_v2 import runtime_snapshot as runtime_snapshot_v2
from radar_pre160_cloud_v3 import evidence_snapshot_v3
from radar_pre160_hardening_persistence_v1 import hardening_status,persist_hardening_snapshot
from radar_pre160_persistence_v1 import pre160_evaluation_status
from radar_pre160_runtime_v4 import build_hardening_snapshot
from radar_pre160_runtime_v4_linkage import apply_safe_linkage

REAL_TRADING=False


def hardening_snapshot_v4():
    evidence=evidence_snapshot_v3();durable=pre160_evaluation_status(365);base=runtime_snapshot_v2();operational=operational_pipeline()
    try:authority=hardening_status(1000)
    except Exception as exc:authority={'status':'HARDENING_AUTHORITY_DEGRADED','checkpoints':[],'envelopes':[],'error':str(exc)[:500],'real_trading':False}
    snapshot=build_hardening_snapshot(evidence_v3=evidence,durable_eval=durable,evidence_authority=authority,
                                      forward_records=operational.get('forward_records') or [],base_runtime=base)
    envelopes=(authority.get('envelopes') or []) or (snapshot.get('envelopes_to_freeze') or [])
    snapshot=apply_safe_linkage(snapshot,(durable or {}).get('decisions') or [],envelopes)
    snapshot['authority_before_persist']={'status':authority.get('status'),'checkpoint_records':authority.get('checkpoint_records',0),
                                          'checkpoint_integrity':authority.get('checkpoint_integrity'),'envelope_records':authority.get('envelope_records',0)}
    # authority_before_persist is diagnostic and part of the persisted object, so hash it too.
    from radar_pre160_runtime_v4 import _hash
    snapshot['real_trading']=False;snapshot['snapshot_hash']=_hash({k:v for k,v in snapshot.items() if k!='snapshot_hash'});return snapshot


def persist_hardening_cycle():
    snapshot=hardening_snapshot_v4();result=persist_hardening_snapshot(snapshot)
    return {'status':result.get('status'),'observed_at':snapshot.get('observed_at'),'snapshot_hash':snapshot.get('snapshot_hash'),
            'checkpoint':result.get('checkpoint'),'envelopes':result.get('envelopes'),'readiness_countdown':snapshot.get('readiness_countdown'),
            'setup_allowed':False,'automatic_release':False,'automatic_promotion':False,'automatic_demotion':False,'can_trade':False,'real_trading':False}


def hardening_authority_report(limit=500):
    a=hardening_status(limit);checkpoints=list(a.get('checkpoints') or []);envelopes=list(a.get('envelopes') or [])
    return {'status':a.get('status'),'observed_at':datetime.now(timezone.utc).isoformat(),'checkpoint_records':len(checkpoints),
            'checkpoint_integrity':a.get('checkpoint_integrity'),'latest_checkpoint':checkpoints[-1] if checkpoints else None,
            'envelope_records':len(envelopes),'strategy_versions_missing':a.get('strategy_versions_missing',0),'guard':a.get('guard'),
            'setup_allowed':False,'automatic_release':False,'automatic_promotion':False,'automatic_demotion':False,'can_trade':False,'real_trading':False}


def tasks_111_130_audit():
    try:s=hardening_snapshot_v4()
    except Exception as exc:return {'status':'DEGRADED','error':str(exc)[:700],'tasks':{},'setup_allowed':False,'can_trade':False,'real_trading':False}
    c=s.get('checkpoint_continuity') or {};p=s.get('decision_envelope_provenance') or {};m=s.get('horizon_maturity') or {};cal=s.get('calibration_uncertainty') or {};bm=s.get('multi_benchmark_robustness') or {}
    t=s.get('turnover_cost_budget') or {};x=s.get('concentration_exposure') or {};r=s.get('regime_coverage') or {};pair=s.get('paired_champion_challenger') or {};sup=s.get('sequential_superiority') or {};deg=s.get('persistent_degradation') or {};count=s.get('readiness_countdown') or {}
    tasks={
      '111':'IMPLEMENTED_'+str(c.get('status')),
      '112':'IMPLEMENTED_'+('GAPS_DETECTED' if c.get('gaps') else 'CADENCE_WATCH'),
      '113':'IMPLEMENTED_IDENTITY_FREEZE_'+('VERSION_PENDING' if p.get('strategy_versions_missing') else 'VERSION_CAPTURED'),
      '114':'IMPLEMENTED_PIT_REGIME_ONLY',
      '115':'IMPLEMENTED_BENCHMARK_REFERENCE_FREEZE',
      '116':'IMPLEMENTED_OBSERVED_COST_FREEZE',
      '117':'IMPLEMENTED_PIT_PROVIDER_PROVENANCE',
      '118':'IMPLEMENTED_DETERMINISTIC_ENVELOPE_HASH',
      '119':'IMPLEMENTED_'+str(m.get('status')),
      '120':'IMPLEMENTED_'+str(cal.get('status')),
      '121':'IMPLEMENTED_'+str(bm.get('status')),
      '122':'IMPLEMENTED_'+str(t.get('status')),
      '123':'IMPLEMENTED_'+str(x.get('status')),
      '124':'IMPLEMENTED_'+str(r.get('status')),
      '125':'IMPLEMENTED_'+str(pair.get('status')),
      '126':'IMPLEMENTED_'+str(sup.get('status'))+'_NO_AUTO_PROMOTION',
      '127':'IMPLEMENTED_'+str(deg.get('status'))+'_NO_AUTO_DEMOTION',
      '128':'IMPLEMENTED_'+str(count.get('status'))+'_CONDITIONAL_ONLY',
      '129':'IMPLEMENTED_DURABLE_HARDENING_AUDIT',
      '130':'IMPLEMENTED_PENDING_CI_REDEPLOY_PROOF',
    }
    return {'status':'PRE160_TASKS_111_130','tasks':tasks,'snapshot_hash':s.get('snapshot_hash'),'readiness_countdown':count,
            'setup_allowed':False,'automatic_release':False,'automatic_promotion':False,'automatic_demotion':False,'can_trade':False,'real_trading':False}
