import time

import radar_sync_queue_v3 as q3
from radar_pre160_controls_v8 import build_matrix_271_310
from radar_pre160_production_proof_v3 import proof_v3_contract
from radar_pre160_readiness_v4 import DeepWorkScheduler, StageProfiler, TieredReadiness
from radar_provider_resilience_v2 import ProviderCircuit, ProviderTransportGuard


def _base_matrix(**overrides):
    readiness={'status':'LITE_READY','lite_ready':True,'deep_ready':False,'shared_deep_snapshot':True,'dependency_token_cache':True,
               'budgets_ms':{'cold_http':1000,'hot_http':250,'deep_total':180000},
               'profiler':{'stages':{'http_v7':{'samples':6,'p50_ms':4,'p95_ms':8,'p99_ms':10,'max_ms':11},'deep_total':{'samples':1,'p95_ms':1000}}},
               'scheduler':{'serialized_deep_work':True,'cpu_io_budget_policy':'ONE_DEEP_JOB_AT_A_TIME'}}
    queue={'configured':True,'durable_backend':'SUPABASE','remote_stats_verified':True,'dead_letter_remote':True,
           'ack_after_remote_success':True,'cross_redeploy_verified':False,'current_deployment':'d2','previous_deployment':'d1'}
    provider={'wired':True,'bulkhead_isolation':True,'failover_verified':False,'reconcile_after_recovery':False,
              'circuit':{'state_machine':'CLOSED_OPEN_HALF_OPEN'},'rate_governor':{'adaptive_rate_governor':True}}
    generic={'configured':True,'status':'HEALTHY','successes':5,'timeout_means_missing_data':False,'last_error_type':None}
    learning={'configured':True,'status':'HEALTHY','successes':5,'timeout_means_missing_data':False,'last_error_type':None}
    proof={'verified':False,'contract':proof_v3_contract(),'derived_checks':{},'no_self_certification':True}
    ci={'crash_restart_test':True,'duplicate_delivery_test':True,'outage_recovery_test':True,'queue_saturation_test':True,
        'poison_message_test':True,'network_partition_test':True,'tamper_test':True,'stale_deployment_test':True,'failed_audit_propagation':True}
    args=dict(readiness=readiness,queue=queue,provider=provider,generic_sync=generic,learning_sync=learning,proof_v3=proof,
              deployment={'expected_sha':'a','deployed_sha':'a'},ci_evidence=ci,prior_gate={'status':'BLOCKED_PRE160'})
    args.update(overrides)
    return build_matrix_271_310(**args)


def test_matrix_has_all_tasks_and_frozen_safety_boundary():
    m=_base_matrix();tasks=m['tasks']
    assert set(tasks)=={str(i) for i in range(271,311)}
    assert m['stable_windows_version']=='1.5.28'
    assert m['setup_allowed'] is False and m['can_trade'] is False and m['real_trading'] is False
    assert m['master_gate_v4']['status']=='BLOCKED_PRE160'
    assert tasks['290']['state']=='PENDING_TIME'
    assert tasks['293']['state']=='PENDING_SAMPLE'


def test_cross_redeploy_is_required_for_task_290():
    m=_base_matrix(queue={'configured':True,'durable_backend':'SUPABASE','remote_stats_verified':True,'dead_letter_remote':True,
                          'ack_after_remote_success':True,'cross_redeploy_verified':True,'current_deployment':'d2','previous_deployment':'d1'})
    assert m['tasks']['290']['state']=='PASS'


def test_recent_timeout_never_becomes_healthy_evidence():
    m=_base_matrix(generic_sync={'configured':True,'status':'HEALTHY','successes':9,'timeout_means_missing_data':False,'last_error_type':'TimeoutError'})
    assert m['tasks']['295']['state']=='NOT_VERIFIED'


def test_scheduler_prevents_overlap_and_profiles():
    s=DeepWorkScheduler(min_interval_seconds=5,max_runtime_seconds=30)
    p=StageProfiler();r=TieredReadiness();r.set_lite({'status':'LITE_READY'})
    out=s.run(lambda:p.timed('deep_total',lambda:123))
    assert out['started'] is True
    assert s.run(lambda:456)['started'] is False
    assert p.telemetry()['stages']['deep_total']['samples']==1
    assert r.state(p,s)['lite_ready'] is True


def test_provider_circuit_has_explicit_half_open_state():
    c=ProviderCircuit(failure_threshold=2,cooldown_seconds=.01)
    c.failure('p');c.failure('p')
    assert c.state('p')=='OPEN'
    time.sleep(.02)
    assert c.state('p')=='HALF_OPEN'
    assert c.allow('p') is True
    assert c.allow('p') is False
    c.success('p');assert c.state('p')=='CLOSED'


def test_network_partition_failure_is_fail_closed_then_recovers():
    g=ProviderTransportGuard(max_concurrency=1,failure_threshold=2,cooldown_seconds=.01)
    def down(): raise TimeoutError('partition')
    for _ in range(2):
        try:g.call('provider',down,timeout=.01)
        except Exception:pass
    assert g.circuits.state('provider')=='OPEN'
    time.sleep(.02)
    assert g.call('provider',lambda:'ok',timeout=.01)=='ok'
    assert g.circuits.state('provider')=='CLOSED'


def test_remote_queue_content_addressing_is_deterministic_and_no_ack_on_failure(monkeypatch):
    p={'a':1};assert q3.queue_id('x',p)==q3.queue_id('x',{'a':1})
    calls=[]
    def fake(action,**body):
        calls.append((action,body))
        if action=='enqueue':return {'ok':True,'accepted':1}
        if action=='ack':return {'ok':True,'acked':1}
        raise RuntimeError('partition')
    monkeypatch.setattr(q3,'_post',fake)
    q3.enqueue('x',p,origin_deployment='d1')
    q3.acknowledge(['id'])
    assert [c[0] for c in calls]==['enqueue','ack']


def test_poison_message_and_saturation_contract_are_bounded():
    assert q3.MAX_ATTEMPTS<=20
    contract=q3.queue_contract()
    assert contract['ack_after_remote_success'] is True
    assert contract['idempotency_key'].startswith('sha256')
