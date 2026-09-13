import radar_validation_intelligence_91_100_v1 as m

def _row(i=0,h='1d',reg='bull',ret=.01):
    return {'prediction_id':str(i),'created_at':f'2026-09-{1+i%20:02d}T00:00:00Z','evaluated_at':f'2026-09-{2+i%20:02d}T00:00:00Z',
            'horizon':h,'uncertainty':{'regime':reg},'matured':True,'natural':True,'excess_return':ret,'net_return':ret,
            'cost':.001,'benchmark_return':0.0,'quality_checks':{'pit_valid':True},'real_trading':False}

def test_board_exact_91_100_and_no_live_authority():
    b=m.board([])
    assert set(b['tasks'])=={str(i) for i in range(91,101)}
    assert b['real_trading'] is False
    assert b['live_execution_allowed'] is False
    assert b['automatic_promotion'] is False
    assert b['automatic_release'] is False
    assert b['setup_1_6_allowed'] is False

def test_readiness_requires_audited_30d_and_runtime_restore():
    rows=[_row(i,'1d','bull') for i in range(40)]+[_row(i,'1w','bear') for i in range(40)]
    r=m.autonomous_paper_readiness_v2(rows,None,True,True)
    assert r['status']=='BLOCKED'
    assert '30d_valid_forward_maturity_not_verified' in r['blockers']
    assert r['wall_clock_credit_forbidden'] is True

def test_proof_package_calendar_span_never_counts_as_maturity():
    rows=[_row(i) for i in range(40)]
    p=m.paper_30d_proof_package(rows,None)
    assert p['status']=='PENDING_30D_PROOF'
    assert p['calendar_span_is_not_maturity_credit'] is True

def test_horizon_validation_does_not_infer_missing_horizons():
    rows=[_row(i,'1d','bull') for i in range(30)]
    h=m.multi_horizon_validation(rows)
    assert h['status']=='PARTIAL_1D_ONLY'
    assert h['qualified_horizons']==['1d']
    assert h['no_horizon_inference'] is True

def test_backfilled_rows_do_not_enter_natural_maturity():
    rows=[_row(i) for i in range(30)]
    rows[0]['natural']=False
    q=m.evidence_quality_v2(rows)
    assert q['n_matured_natural']==29
    assert q['backfill_cannot_improve_score'] is True
