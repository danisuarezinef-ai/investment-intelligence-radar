import json

import pytest

import radar_operational_health_v2 as oh
import radar_provider_resilience_v2 as pr
import radar_supabase_sync_partitioned_v2 as ps
import radar_pre160_production_proof_v3 as proof3


def test_failed_partition_is_durably_enqueued_before_cursor_can_advance(monkeypatch):
    sent=[];cursors=[];queued=[]
    def post(payload,timeout=None):
        sent.append(payload)
        if len(sent)==2: raise TimeoutError('controlled partition failure')
        return {'ok':True}
    monkeypatch.setattr(ps.base,'_post',post)
    monkeypatch.setattr(ps.base,'_control_set',lambda k,v:cursors.append((k,v)))
    monkeypatch.setattr(ps.remote_queue,'enqueue',lambda channel,payload: queued.append((channel,payload)) or {'id':'q','real_trading':False})
    with pytest.raises(TimeoutError):
        ps._send_family('events','information_events',[{'id':i} for i in range(5)],cursor_key='cursor',cursor_value=5,chunk_size=2)
    assert cursors==[]
    assert len(queued)==1
    assert queued[0][0]=='generic_sync:events'
    assert len(queued[0][1]['information_events'])==2


def test_backpressure_drain_consumes_only_generic_sync_and_acks_after_success(monkeypatch):
    due=[
        {'id':'g1','channel':'generic_sync:events','payload':{'node_id':'n','information_events':[{'id':1}]}},
        {'id':'probe','channel':'pre160_durability_probe','payload':{'kind':'probe'}},
    ]
    calls=[];acks=[];fails=[]
    monkeypatch.setattr(ps.remote_queue,'enabled',lambda:True)
    monkeypatch.setattr(ps.remote_queue,'due',lambda limit:due)
    monkeypatch.setattr(ps.base,'_post',lambda payload: calls.append(payload) or {'ok':True})
    monkeypatch.setattr(ps.remote_queue,'acknowledge',lambda ids:acks.extend(ids) or {'ok':True})
    monkeypatch.setattr(ps.remote_queue,'fail',lambda items:fails.extend(items) or {'ok':True})
    out=ps.drain_backpressure()
    assert out['eligible']==1 and out['drained']==1 and out['failed']==0
    assert len(calls)==1 and acks==['g1'] and fails==[]


def test_controlled_provider_probe_observes_circuit_and_rate_recovery():
    out=pr.controlled_resilience_probe()
    assert out['status']=='PASS'
    assert out['circuit_open_verified'] is True
    assert out['half_open_verified'] is True
    assert out['recovery_verified'] is True
    assert out['rate_limit_backoff_verified'] is True
    assert out['rate_recovery_gradual_verified'] is True
    assert out['external_provider_failover_verified'] is False
    assert out['investment_data_used'] is False and out['real_trading'] is False


def test_operational_health_is_separate_from_investment_scoring():
    out=oh.operational_health(
        generic_sync={'status':'HEALTHY','configured':True,'successes':4},
        learning_sync={'status':'HEALTHY','configured':True,'successes':4},
        queue={'configured':True,'remote_stats_verified':True,'cross_redeploy_verified':True},
        provider={'wired':True},readiness={'lite_ready':True,'deep_ready':True},
        partition={'partitioned':True,'failed_cycles':0})
    assert out['status']=='HEALTHY'
    assert out['investment_score_included'] is False
    assert out['affects_investment_ranking'] is False
    assert out['affects_model_promotion'] is False
    assert out['real_trading'] is False


def test_worker_utilization_marks_unknown_workers_as_not_instrumented_not_zero():
    out=oh.worker_utilization(generic_sync={},learning_sync={},partition={},readiness={},queue={},provider={})
    assert out['workers']['closed_loop_paper']['instrumentation']=='NOT_INSTRUMENTED_FOR_CPU_UTILIZATION'
    assert out['not_instrumented_is_not_zero'] is True
    assert out['global_heavy_scheduler_required'] is False


def test_proof_v3_rejects_light_only_prior_group_even_if_labeled_pass(tmp_path,monkeypatch):
    monkeypatch.setattr(proof3,'protected_digest',lambda root:{'digest':'abc','files':1,'missing':[]})
    payload={
        'audit_conclusion':'success','protected_digest':'abc','audited_commit_sha':'a','railway_deployed_sha':'a',
        'stable_windows_version':'1.5.28','real_trading':False,'audit_run_id':'run',
        'checks':{
            'tasks_151_200':{'status':'PASS','evidence':{'http_200':True,'source_ready':True,'deep_ready':False,'real_trading':False}},
            'tasks_201_270':{'status':'PASS','evidence':{'http_200':True,'source_ready':True,'deep_ready':True,'real_trading':False}},
            'dual_sync':{'status':'PASS','evidence':{'ok':True}},'queue_remote':{'status':'PASS','evidence':{'ok':True}},
            'tamper_test':{'status':'PASS','evidence':{'ok':True}},'stale_deployment_test':{'status':'PASS','evidence':{'ok':True}},
            'failed_audit_propagation':{'status':'PASS','evidence':{'ok':True}},
        }}
    (tmp_path/proof3.DEFAULT_PATH).write_text(json.dumps(payload),encoding='utf-8')
    out=proof3.verify_proof_v3(tmp_path)
    assert out['verified'] is False
    assert out['derived_checks']['tasks_151_200'] is False


def test_proof_v3_accepts_deep_prior_groups_when_every_external_check_is_valid(tmp_path,monkeypatch):
    monkeypatch.setattr(proof3,'protected_digest',lambda root:{'digest':'abc','files':1,'missing':[]})
    deep={'status':'PASS','evidence':{'http_200':True,'source_ready':True,'deep_ready':True,'real_trading':False}}
    payload={'audit_conclusion':'success','protected_digest':'abc','audited_commit_sha':'a','railway_deployed_sha':'a',
        'stable_windows_version':'1.5.28','real_trading':False,'audit_run_id':'run','checks':{
            'tasks_151_200':deep,'tasks_201_270':deep,
            'dual_sync':{'status':'PASS','evidence':{'ok':True}},'queue_remote':{'status':'PASS','evidence':{'ok':True}},
            'tamper_test':{'status':'PASS','evidence':{'ok':True}},'stale_deployment_test':{'status':'PASS','evidence':{'ok':True}},
            'failed_audit_propagation':{'status':'PASS','evidence':{'ok':True}}}}
    (tmp_path/proof3.DEFAULT_PATH).write_text(json.dumps(payload),encoding='utf-8')
    assert proof3.verify_proof_v3(tmp_path)['verified'] is True
