from radar_autonomous_runtime_v3 import autonomous_cycle,REAL_TRADING


def _base(**kw):
    x=dict(freshness_ok=True,degraded=False,promotion_ready=True,maturity_status='EARLY_EVIDENCE',
           paper_authority_ready=True,persistence_ok=True,forward_integrity_ok=True,paper_state_ok=True,
           duplicate_risk=False,account={'equity':1000.0,'cash':1000.0},positions=[],drawdown_pct=0.0,
           allocations=[],prices={},proposed_turnover_pct=0.0,estimated_cost_bps=5.0,expected_return_bps=30.0)
    x.update(kw);return x


def test_runtime_never_real_trading():
    r=autonomous_cycle(**_base())
    assert REAL_TRADING is False and r['real_trading'] is False and r['real_order_submission'] is False
    assert r['state']=='PAPER_ACTIVE'


def test_stale_cloud_forces_hold():
    r=autonomous_cycle(**_base(freshness_ok=False))
    assert r['state']=='HOLD' and 'STALE_CLOUD' in r['blockers']
    assert r['paper_execution']['executed']==[]


def test_duplicate_risk_forces_hold():
    r=autonomous_cycle(**_base(duplicate_risk=True))
    assert r['state']=='HOLD' and 'DUPLICATE_EXECUTION_RISK' in r['blockers']


def test_missing_cost_or_edge_forces_hold():
    r=autonomous_cycle(**_base(estimated_cost_bps=None))
    assert r['state']=='HOLD' and 'COST_NOT_VERIFIED' in r['blockers']


def test_risk_budget_forces_hold():
    positions=[{'symbol':'X','market_value':900.0,'sector':'TEST'}]
    r=autonomous_cycle(**_base(account={'equity':1000.0,'cash':100.0},positions=positions))
    assert r['state']=='HOLD' and 'PAPER_RISK_BUDGET_BLOCKED' in r['blockers']


def test_brain_growth_is_decoupled_from_real_execution():
    r=autonomous_cycle(**_base())
    assert r['learning_may_continue'] is True
    assert r['self_improvement_scope']=='PROPOSE_TEST_VALIDATE_SHADOW_PAPER'
    assert r['real_trading'] is False
