import radar_learning_governance_121_130_v1 as m

def test_exact_tasks_and_hard_locks():
    b=m.board([])
    assert list(b['tasks'])==[str(x) for x in range(121,131)]
    assert b['real_trading'] is False and b['live_execution_allowed'] is False
    assert b['automatic_promotion'] is False and b['automatic_release'] is False and b['setup_1_6_allowed'] is False

def test_feature_authority_fails_without_full_snapshot():
    x=m.feature_snapshot_authority([{'prediction_id':'p1','captured_at':'2026-09-01T00:00:00Z','features':{}}])
    assert x['status']=='FAIL_CLOSED' and x['backfill_allowed'] is False and x['reconstruction_allowed'] is False

def test_feature_authority_accepts_prospective_immutable_vector():
    x=m.feature_snapshot_authority([{'prediction_id':'p1','captured_at':'2026-09-01T00:00:01Z','data_cutoff':'2026-09-01T00:00:00Z',
        'feature_fingerprint':'abc','features':{'momentum7':.1},'immutable':True,'prospective_capture':True,
        'lookahead':False,'backfilled':False,'retroactive_fill':False,'source':'decision_forward_ledger.payload.features'}])
    assert x['status']=='PASS' and x['valid_n']==1 and x['temporal_alignment_required'] is True

def test_horizon_borrowing_forbidden():
    rows=[]
    for i in range(25):rows.append({'matured':True,'natural':True,'horizon':'1d','excess_return':.01})
    x=m.multi_horizon_outcome_evaluator(rows)
    assert x['horizons']['1d']['status']=='PASS'
    assert x['horizons']['1w']['status']=='PENDING_SAMPLE'
    assert x['horizon_borrowing_forbidden'] is True

def test_demotion_can_only_reduce_paper_risk():
    rows=[]
    for i in range(20):rows.append({'matured':True,'natural':True,'created_at':f'2026-08-{i%20+1:02d}T00:00:00Z','model_version':'m','excess_return':.01})
    for i in range(20):rows.append({'matured':True,'natural':True,'created_at':f'2026-09-{i%20+1:02d}T00:00:00Z','model_version':'m','excess_return':-.01})
    x=m.automatic_demotion_safety(rows,'m')
    assert x['degraded'] is True and x['can_promote_replacement'] is False and x['live_effect'] is False

def test_portfolio_construction_requires_upstream_survival_liquidity_es_correlation():
    c=[{'decision_state':'BUY','symbol':'MSFT','horizon':'1d','confidence':.8,'uncertainty':{'regime':'bull'}}]
    blocked=m.portfolio_construction_v2(c,{'survival_gate_pass':False})
    assert blocked['status']=='BLOCKED_EVIDENCE' and blocked['allocations']==[]
    ok=m.portfolio_construction_v2(c,{'survival_gate_pass':True,'liquidity_verified':True,'expected_shortfall_verified':True,'correlation_verified':True})
    assert ok['status']=='PASS' and ok['sum_weights']<=.70 and ok['allocations'][0]['paper_weight']<=.20

def test_master_gate_requires_30d_and_critical_tasks():
    tasks={str(n):'PASS' for n in (28,29,80,99,113,119,121,122,124,128,129)}
    rt={'lease_held':True,'durable_sync':'RECONCILED','exact_restore':True}
    assert m.master_paper_control_gate(tasks,rt,719)['status']=='BLOCKED'
    assert m.master_paper_control_gate(tasks,rt,720)['status']=='PASS'
    assert m.master_paper_control_gate(tasks,rt,720)['live_execution_allowed'] is False

def test_governor_freezes_on_integrity_failure():
    x=m.autonomous_learning_governor({'critical_integrity':False})
    assert x['status']=='FAIL_CLOSED' and x['mode']=='FREEZE_ALL_LEARNING' and x['automatic_live_promotion'] is False
