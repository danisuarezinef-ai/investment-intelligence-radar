import radar_runtime_31_40_v1 as r


def test_31_persistence_quorum_passes_only_exact_reconciled_paper():
    out=r.task31_persistence_quorum(
        lease={'held':True,'session_id':'s','real_trading':False},
        core={'status':'RESTORED_EXACT_AUTONOMY_CORE','backfill_used':False,'real_trading':False},
        checkpoint={'status':'RESTORED_EXACT_PAPER_ENGINE','verified':True,'backfill_used':False,'real_trading':False},
        reconciliation={'status':'RECONCILED'})
    assert out['status']=='PASS'
    assert out['live_execution_allowed'] is False


def test_32_forward_continuity_rejects_rewind():
    out=r.task32_forward_continuity({'records':9,'matured':2,'capture_started_at':'x','backfill_used':False,'reconstructed':False,'real_trading':False},
                                    {'records':10,'matured':2,'capture_started_at':'x'})
    assert out['status']=='FAIL_CLOSED'
    assert 'records_monotonic' in out['blockers']


def test_33_journal_coverage_is_partial_for_legacy_gap():
    out=r.task33_journal_coverage({'decision_rows':1096,'context_rows':48,'prospective_decision_rows':1096,'prospective_context_rows':48})
    assert out['status']=='PARTIAL'
    assert out['retroactive_fill_allowed'] is False


def test_34_point_in_time_requires_complete_provenance():
    out=r.task34_point_in_time_provenance({'decision_rows':100,'pit_rows':100,'nonretro_rows':100,'paper_rows':100})
    assert out['status']=='PASS'


def test_35_maturity_scheduler_never_uses_future_or_backfill():
    out=r.task35_maturity_scheduler({'1d':{'n':10,'matured':11},'1w':{},'1m':{},'3m':{}})
    assert out['status']=='FAIL_CLOSED'


def test_36_dependency_budget_fails_for_critical_dependency():
    out=r.task36_dependency_error_budget([{'name':'lease','critical':True,'status':'TIMEOUT'}])
    assert out['status']=='FAIL_CLOSED'


def test_37_recovery_ledger_requires_exact_identity():
    out=r.task37_recovery_ledger([{'recovery_mode':'EXACT_PAPER','state_hash_equal':True,'session_continuity':True,'backfill_used':False,'real_trading':False}])
    assert out['status']=='PASS'


def test_38_replay_readiness_fail_closed_until_reproducible():
    out=r.task38_replay_readiness({'decision_snapshot_hash':'d','market_snapshot_hash':'m','config_hash':'c','model_version':'v','deterministic_output_equal':False,'future_data_used':False,'real_trading':False})
    assert out['status']=='PENDING'


def test_39_learning_integrity_blocks_auto_promotion():
    out=r.task39_learning_integrity({'challenger_only':True,'bounded_mutation':True,'historical_can_promote':False,'automatic_promotion':False,'mutates_active_champion':False,'real_trading':False})
    assert out['status']=='PASS'
    assert out['live_execution_allowed'] is False


def test_40_requires_28_and_29_even_if_31_39_are_safe():
    tasks=[
        {'task':31,'status':'PASS'},{'task':32,'status':'PASS'},{'task':33,'status':'PARTIAL'},
        {'task':34,'status':'PASS'},{'task':35,'status':'PASS'},{'task':36,'status':'PASS'},
        {'task':37,'status':'PENDING_SAMPLE'},{'task':38,'status':'PENDING'},{'task':39,'status':'PASS'}]
    out=r.task40_composite(tasks,task28_status='RECONCILED',task29_status='FAIL')
    assert out['status']=='PENDING'
    assert '29:FAIL' in out['blockers']
    assert out['real_trading'] is False
