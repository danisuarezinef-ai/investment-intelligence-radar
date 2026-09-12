from pathlib import Path

from radar_market_data_authority_v1 import freeze_universe, classify_missing, authority_contract
from radar_pre160_resilience_v7 import build_resilience_tasks, classify_retry
from radar_pre160_data_authority_v7 import build_data_authority_tasks, decision_fingerprint, deterministic_replay
from radar_pre160_statistics_v7 import calibration_metrics, effective_sample_size, benjamini_hochberg, deflated_score, build_statistical_tasks
from radar_pre160_autonomy_v7 import abstention_decision, challenger_incubation, build_autonomy_tasks, master_gate
from radar_pre160_controls_v7 import build_matrix_201_270
from radar_sync_queue_v2 import DurableSyncQueue, queue_contract

ALLOWED={'PASS','PENDING_SAMPLE','PENDING_TIME','NOT_VERIFIED','FAILED'}

def _assert_group(group,start,end):
    tasks=group['tasks'];assert set(tasks)=={str(i) for i in range(start,end+1)}
    assert all(v['state'] in ALLOWED for v in tasks.values())
    assert group['real_trading'] is False

def test_retry_taxonomy_is_bounded_and_validation_does_not_retry():
    assert classify_retry('timeout')['retry'] is True
    assert classify_retry('429')['retry'] is True
    assert classify_retry('409')['backoff']=='RECONCILE_THEN_RETRY'
    assert classify_retry('validation')['retry'] is False
    assert queue_contract()['dead_letter'] is True

def test_durable_queue_is_idempotent_and_moves_terminal_failures_to_dlq(tmp_path):
    q=DurableSyncQueue(str(tmp_path/'q.sqlite3'),max_attempts=2)
    a=q.enqueue('sync',{'x':1});b=q.enqueue('sync',{'x':1});assert a==b and q.stats()['queued']==1
    assert q.fail(a,'timeout',1)=='RETRY';assert q.fail(a,'timeout',1)=='DEAD_LETTER'
    s=q.stats();assert s['queued']==0 and s['dead_letter']==1 and s['real_trading'] is False

def test_market_data_authority_is_point_in_time_and_missing_is_not_zero():
    snap=freeze_universe('2026-09-12T00:00:00Z',[{'symbol':'AAA','listed_at':'2020-01-01T00:00:00Z'},{'symbol':'OLD','listed_at':'2010-01-01T00:00:00Z','delisted_at':'2020-01-01T00:00:00Z'}])
    assert [x['eligible'] for x in snap['members']]==[True,False]
    assert classify_missing('provider_failure')['zero_evidence'] is False
    assert authority_contract()['raw_records_mutated'] is False

def test_lineage_fingerprint_and_replay_are_deterministic():
    fp1=decision_fingerprint(data_hash='a',feature_hash='b',model_hash='c',strategy_hash='d',context_hash='e')
    fp2=decision_fingerprint(data_hash='a',feature_hash='b',model_hash='c',strategy_hash='d',context_hash='e')
    assert fp1==fp2 and len(fp1)==64
    assert deterministic_replay({'a':1},{'a':1})['status']=='PASS'
    assert deterministic_replay({'a':1},{'a':2})['status']=='FAILED'

def test_statistics_are_real_computations_not_static_passes():
    cal=calibration_metrics([{'probability':.8,'outcome':True},{'probability':.2,'outcome':False}])
    assert cal['n']==2 and cal['brier'] is not None and cal['ece'] is not None
    assert effective_sample_size([1,1,1,1])==4
    bh=benjamini_hochberg([.001,.02,.5]);assert bh['m']==3 and 0 in bh['rejected_indices']
    assert deflated_score(1.0,100,20)<1.0

def test_autonomy_fails_closed_and_abstention_has_live_veto():
    c=challenger_incubation({'forward_n':3,'forward_days':2,'forward_only':True,'matured_only':True})
    assert c['eligible'] is False and c['automatic_promotion'] is False
    a=abstention_decision(expected_edge=.001,uncertainty=.1,tail_risk=.2,data_ok=False,calibration_ok=False)
    assert a['decision']=='ABSTAIN' and a['live_execution_allowed'] is False and a['real_trading'] is False
    gate=master_gate([{'tasks':{'1':{'state':'PASS','critical':True},'2':{'state':'PENDING_SAMPLE','critical':True}}}])
    assert gate['status']=='BLOCKED_PRE160' and gate['setup_allowed'] is False and gate['automatic_release'] is False

def test_all_201_270_tasks_exist_and_missing_evidence_never_promotes():
    proof={'status':'NOT_VERIFIED','verified':False,'real_trading':False}
    health={'status':'HEALTHY','configured':True,'timeout_means_missing_data':False,'last_latency_ms':100,
            'learning_sync':{'status':'HEALTHY','configured':True,'last_latency_ms':100,'timeout_means_missing_data':False}}
    prior={'tasks':{'151':{'state':'PASS','critical':True}},'real_trading':False}
    matrix=build_matrix_201_270(evidence={},hardening={},runtime={},supabase_health=health,proof=proof,
        cache_telemetry={'prewarm_enabled':True,'async_refresh':True,'stale_while_revalidate':True,'dependency_keys':True},prior_task_groups=[prior])
    assert set(matrix['tasks'])=={str(i) for i in range(201,271)}
    assert all((v or {}).get('state') in ALLOWED for v in matrix['tasks'].values())
    assert matrix['tasks']['201']['state']=='NOT_VERIFIED'
    assert matrix['tasks']['270']['state']=='NOT_VERIFIED'
    assert matrix['setup_allowed'] is False and matrix['automatic_release'] is False and matrix['real_trading'] is False

def test_individual_groups_have_exact_task_ranges():
    r=build_resilience_tasks(proof={},deployment={},endpoint_metrics={},cache={},supabase_health={},provider_controls={},queue={},roundtrip_ms=None)
    _assert_group(r,201,220)
    d=build_data_authority_tasks(evidence={},hardening={},runtime={},metadata={})
    _assert_group(d,221,240)
    s=build_statistical_tasks(evidence={},runtime={},samples={})
    _assert_group(s,241,260)
    a=build_autonomy_tasks(runtime={},evidence={},task_groups=[])
    _assert_group(a,261,270)

def test_cloud_v8_is_composed_over_v7_over_v6_and_windows_stays_frozen():
    cloud7=Path('cloud_service_v7.py').read_text(encoding='utf-8')
    cloud8=Path('cloud_service_v8.py').read_text(encoding='utf-8')
    start=Path('start.sh').read_text(encoding='utf-8')
    version=__import__('json').loads(Path('version.json').read_text(encoding='utf-8-sig'))['version']
    assert 'import cloud_service_v6 as base6' in cloud7
    assert 'base6.start_runtime()' in cloud7
    assert '/pre160-audit-201-270-v1' in cloud7 and '/pre160-master-gate-v3' in cloud7
    assert 'import cloud_service_v7 as base7' in cloud8
    assert 'base7.start_runtime()' in cloud8
    assert 'cloud_service_v8.py' in start
    assert version=='1.5.28'
    assert 'REAL_TRADING=False' in cloud8.replace(' ','')
