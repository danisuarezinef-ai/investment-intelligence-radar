"""Aggregation layer for pre-1.6 tasks 201-270."""
from __future__ import annotations
import os,time

from radar_market_data_authority_v1 import authority_contract
from radar_raw_vault_v1 import RawVault
from radar_sync_queue_v2 import queue_contract
from radar_pre160_resilience_v7 import build_resilience_tasks
from radar_pre160_data_authority_v7 import build_data_authority_tasks, content_hash
from radar_pre160_statistics_v7 import build_statistical_tasks
from radar_pre160_autonomy_v7 import build_autonomy_tasks, master_gate

REAL_TRADING=False


def _d(v):return v if isinstance(v,dict) else {}
def _rows(v):return v if isinstance(v,list) else []

def _candidate_rows(runtime):
    rows=[]
    for r in _rows(runtime.get('scorecards')):
        if not isinstance(r,dict):continue
        rows.append({
            'model_version':r.get('model_version') or r.get('version') or r.get('key') or r.get('name'),
            'forward_n':int(r.get('forward_n') or r.get('n_forward') or 0),
            'forward_days':float(r.get('forward_days') or 0),
            'forward_only':r.get('forward_only') is True,
            'matured_only':r.get('matured_only') is True,
            'backfilled':r.get('backfilled') is True,
            'eligible':r.get('eligible') is True,
            'base_score':float(r.get('score') or r.get('forward_score') or 0),
            'regime':r.get('regime'),'horizon':r.get('horizon'),'asset_class':r.get('asset_class'),
            'uncertainty':r.get('uncertainty'),'expected_edge':r.get('expected_edge'),'tail_risk':r.get('tail_risk'),
        })
    return rows

def build_matrix_201_270(*, evidence,hardening,runtime,supabase_health,proof,cache_telemetry,
                         prior_task_groups=None,endpoint_metrics=None,statistical_samples=None,
                         deployment=None,data_metadata=None,autonomy_samples=None):
    evidence=_d(evidence);hardening=_d(hardening);runtime=_d(runtime);health=_d(supabase_health);proof=_d(proof)
    market=authority_contract();vault=RawVault().contract();prior=list(prior_task_groups or [])

    deployed=(deployment or {}).get('deployed_sha') or os.getenv('RAILWAY_GIT_COMMIT_SHA') or os.getenv('RADAR_DEPLOY_REV')
    expected=(deployment or {}).get('expected_sha') or os.getenv('RADAR_EXPECTED_MAIN_SHA')
    deployment_info={'deployed_sha':deployed,'expected_sha':expected}
    learning=_d(health.get('learning_sync'))
    latencies=[x for x in (health.get('last_latency_ms'),learning.get('last_latency_ms')) if isinstance(x,(int,float))]
    roundtrip=max(latencies) if latencies else None
    provider_controls={
        'circuit_breakers':['supabase-generic','supabase-learning'] if health.get('configured') and learning.get('configured') else [],
        'bulkhead_isolation':False,
        'reconcile_after_recovery':False,
    }
    resilience=build_resilience_tasks(
        proof=proof,deployment=deployment_info,endpoint_metrics=endpoint_metrics or {},cache=cache_telemetry or {},
        supabase_health=health,provider_controls=provider_controls,queue=queue_contract(),roundtrip_ms=roundtrip)

    meta=dict(data_metadata or {})
    meta.setdefault('forward_ledger_authorities',['decision_forward_ledger'])
    meta.setdefault('pit_universe_frozen',False)
    meta.setdefault('survivorship_guard',market.get('survivorship_guard') is True)
    meta.setdefault('corporate_actions_authority',market.get('corporate_actions') is True)
    meta.setdefault('price_field_policy',market.get('price_field_policy'))
    meta.setdefault('market_calendar_authority',False)
    meta.setdefault('missing_data_taxonomy',market.get('missing_data_taxonomy'))
    meta.setdefault('freshness_sla_by_type',market.get('freshness_sla_by_type'))
    meta.setdefault('immutable_raw_vault',vault.get('production_durability_verified') is True)
    meta.setdefault('dataset_hash',evidence.get('snapshot_hash'))
    meta.setdefault('context_hash',hardening.get('snapshot_hash'))
    data=build_data_authority_tasks(evidence=evidence,hardening=hardening,runtime=runtime,metadata=meta)

    stats=build_statistical_tasks(evidence=evidence,runtime=runtime,samples=statistical_samples or {})
    candidates=_candidate_rows(runtime)
    auto=autonomy_samples or {}
    autonomy=build_autonomy_tasks(
        runtime=runtime,evidence=evidence,candidates=auto.get('candidates') or candidates,
        champion_history=auto.get('champion_history') or [],shadow_predictions=auto.get('shadow_predictions') or [],
        diversity_vectors=auto.get('diversity_vectors') or [],correlations=auto.get('correlations') or [],
        routing_context=auto.get('routing_context') or {},task_groups=prior+[resilience,data,stats])

    groups=prior+[resilience,data,stats,autonomy];tasks={}
    for g in groups:tasks.update(_d(g.get('tasks')))
    new_tasks={str(i):tasks.get(str(i)) for i in range(201,271)}
    gate=master_gate(groups)
    critical_failed=[k for k,v in new_tasks.items() if isinstance(v,dict) and v.get('critical') and v.get('state')=='FAILED']
    critical_pending=[k for k,v in new_tasks.items() if isinstance(v,dict) and v.get('critical') and v.get('state')!='PASS']
    return {
        'status':'PRE160_TASKS_201_270','tasks':new_tasks,'groups':{
            '201_220':resilience,'221_240':data,'241_260':stats,'261_270':autonomy},
        'critical_failed':critical_failed,'critical_pending':critical_pending,'master_gate':gate,
        'observed_at_epoch':time.time(),'matrix_digest':content_hash(new_tasks),
        'stable_windows_version':'1.5.28','candidate_version':'1.6.0','setup_allowed':False,'setup_built':False,
        'automatic_release':False,'automatic_promotion':False,'automatic_demotion':False,
        'live_execution_allowed':False,'can_trade':False,'real_trading':False,
    }
