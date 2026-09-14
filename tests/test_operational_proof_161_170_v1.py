import radar_operational_proof_161_170_v1 as m


def test_exact_tasks_and_locks():
    b=m.board();assert list(b['tasks'])==[str(i) for i in range(161,171)]
    assert b['real_trading'] is False and b['live_execution_allowed'] is False
    assert b['automatic_promotion'] is False and b['automatic_release'] is False


def test_source_and_sha_mismatch_fail_closed():
    assert m.source_sync('a','b')['status']=='BLOCKED_SOURCE_MISMATCH'
    assert m.deployed_sha_proof('a','a','b')['status']=='FAIL_CLOSED'


def test_schema_requires_rls_and_no_anon_write():
    good={'objects':['radar_paper_forward_maturity_ledger','radar_append_paper_maturity_interval','radar_paper_valid_forward_hours'],'rls_enabled':True,'anon_write_allowed':False}
    assert m.supabase_schema(good)['status']=='PASS'
    assert m.supabase_schema({**good,'anon_write_allowed':True})['status']=='FAIL_CLOSED'


def test_zero_hours_is_valid_authority_not_fake_maturity():
    a={'status':'AUTHORITY_READY','valid_forward_hours':0.0,'edge_active':True,'real_trading':False}
    assert m.persistence_authority(a)['status']=='PASS'
    assert m.maturity_ledger(a)['status']=='PASS'
    assert m.valid_forward_authority(a)['status']=='PASS'
    assert m.valid_forward_authority(a)['evidence']['valid_forward_hours']==0.0


def test_ci_requires_legacy_controls_preserved():
    assert m.ci_full_chain({'status':'PASS','legacy_controls_preserved':False,'v22_controls_pass':True})['status']=='NOT_VERIFIED'
    assert m.ci_full_chain({'status':'PASS','legacy_controls_preserved':True,'v22_controls_pass':True})['status']=='PASS'
