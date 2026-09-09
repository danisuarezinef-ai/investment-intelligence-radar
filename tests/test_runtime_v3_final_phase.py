import radar_regime_intelligence_v1 as regime
import radar_paper_execution_v2 as paper
import radar_provider_resilience_v1 as providers
import radar_autonomous_loop_v1 as loop
import radar_promotion_governance_v2 as promo
import radar_validation_runtime_v3 as runtime


def test_regime_fail_closed_and_risk_off():
    missing=regime.classify_regime({'volatility_pct':20})
    assert missing['status']=='INSUFFICIENT_EVIDENCE'
    assert missing['risk_multiplier']==0.0
    r=regime.classify_regime({'volatility_pct':35,'trend_pct':-12,'breadth_pct':25})
    assert r['regime']=='RISK_OFF' and r['risk_multiplier']<1
    out=regime.apply_regime_to_candidate({'approved_budget':1000,'confidence':.8},r)
    assert out['adjusted_budget']==450 and out['real_trading'] is False


def test_paper_execution_models_costs_partial_fill_without_broker():
    fill=paper.simulate_fill({'side':'BUY','quantity':100},{'mid_price':10,'available_volume':1000},
                             {'max_participation_rate':.05,'fee_bps':2,'spread_bps':6,'slippage_bps':4})
    assert fill['status']=='PARTIAL'
    assert fill['filled_quantity']==50
    assert fill['fill_price']>10 and fill['fees']>0
    assert paper.execution_shortfall_pct(fill)>0
    assert fill['broker_connected'] is False and fill['can_submit_order'] is False and fill['real_trading'] is False


def test_provider_resilience_opens_circuit_and_checks_consensus():
    p=providers.failover_order([
        {'name':'a','calls':10,'failures':0,'consecutive_failures':0},
        {'name':'b','calls':10,'failures':5,'consecutive_failures':3},
    ])
    assert p['request_order']==['a']
    assert p['providers'][-1]['status']=='OPEN_CIRCUIT'
    assert providers.source_consensus([{'price':100},{'price':100.5}])['status']=='OK'
    assert providers.source_consensus([{'price':100},{'price':110}])['status']=='CONFLICT'


def test_autonomous_loop_never_enables_live_execution():
    blocked=loop.autonomous_cycle({})
    assert blocked['status']=='BLOCKED' and blocked['can_trade'] is False
    complete=loop.autonomous_cycle({
        'market_observation':{},'decision_snapshot':{},'allocation_plan':{'approved':[{'symbol':'AAA'}]},
        'risk_state':{'blocked':False},'shadow_state':{'started':True},'outcome_matured':True,
        'paper_review_approved':True,
    })
    assert complete['status']=='COMPLETE'
    assert complete['paper_execution_allowed'] is True
    assert complete['live_execution_allowed'] is False and complete['real_trading'] is False


def test_promotion_governance_requires_gate_plus_human_and_never_live():
    good={'forward_days':100,'decisions':50,'marks':120,'max_drawdown_pct':-5,
          'benchmark_coverage':1.0,'cost_coverage':1.0,'positive_months':4,
          'oos_pass':True,'degradation_clear':True}
    nohuman=promo.promotion_governance(good,human_approved=False)
    assert nohuman['shadow_gate_passed'] is True and nohuman['paper_execution_allowed'] is False
    yes=promo.promotion_governance(good,human_approved=True)
    assert yes['paper_execution_allowed'] is True
    assert yes['live_execution_allowed'] is False and yes['auto_promote'] is False and yes['real_trading'] is False


def test_runtime_normalizes_forward_coverage_counts(monkeypatch):
    shadow={'forward_days':100,'matured_predictions':100,'benchmark_coverage':94,'cost_coverage':100,
            'max_drawdown_pct':-4,'positive_months':4,'ledger_integrity':True,'pit_verified':True}
    monkeypatch.setattr(runtime,'validation_runtime_snapshot',lambda:{'decision_lab_v5':{},'forward':{},'historical_lab':{},'shadow':shadow})
    monkeypatch.setattr(runtime,'shadow_portfolio_v2_status',lambda:{'started':True,'decisions':50,'marks':120,'real_trading':False})
    out=runtime.validation_runtime_v3(degradation_reference={'samples':30,'hit_rate':.6,'excess_return_pct':5,'brier':.15},
                                      degradation_current={'samples':30,'hit_rate':.6,'excess_return_pct':5,'brier':.15})
    assert out['paper_gate_evidence']['benchmark_coverage']==.94
    assert out['paper_gate_evidence']['cost_coverage']==1.0
    assert 'benchmark_coverage' in out['shadow_to_paper_governance_v2']['gate']['failed']


def test_runtime_blocks_paper_fill_until_gate_and_human_approval(monkeypatch):
    monkeypatch.setattr(runtime,'validation_runtime_snapshot',lambda:{'decision_lab_v5':{},'forward':{},'historical_lab':{},'shadow':{}})
    monkeypatch.setattr(runtime,'shadow_portfolio_v2_status',lambda:{'started':True,'decisions':0,'marks':0,'real_trading':False})
    blocked=runtime.validation_runtime_v3(paper_order={'side':'BUY','quantity':10},paper_market={'mid_price':10,'available_volume':1000})
    assert blocked['paper_execution_v2']['status']=='BLOCKED_BY_PROMOTION'
    good={'forward_days':100,'decisions':50,'marks':120,'max_drawdown_pct':-5,'benchmark_coverage':1.0,
          'cost_coverage':1.0,'positive_months':4,'oos_pass':True,'degradation_clear':True}
    allowed=runtime.validation_runtime_v3(paper_evidence=good,human_paper_approval=True,
        paper_order={'side':'BUY','quantity':10},paper_market={'mid_price':10,'available_volume':1000})
    assert allowed['paper_execution_v2']['status']=='FILLED'
    assert allowed['paper_execution_v2']['broker_connected'] is False
    assert allowed['live_execution_allowed'] is False and allowed['real_trading'] is False


def test_runtime_v3_is_read_only_and_does_not_claim_performance(monkeypatch):
    monkeypatch.setattr(runtime,'validation_runtime_snapshot',lambda:{'decision_lab_v5':{},'forward':{},'historical_lab':{},'shadow':{}})
    monkeypatch.setattr(runtime,'shadow_portfolio_v2_status',lambda:{'started':False,'real_trading':False})
    out=runtime.validation_runtime_v3()
    assert out['runtime_version']=='v3'
    assert out['strategy_performance_verified'] is False
    assert 'NOT VERIFIED' in out['performance_note']
    assert out['live_execution_allowed'] is False and out['can_trade'] is False and out['real_trading'] is False


def test_windows_ci_concurrency_isolated_by_event_and_ref():
    source=open('.github/workflows/windows-release.yml',encoding='utf-8').read()
    assert 'github.event_name' in source
    assert 'github.event.pull_request.number || github.ref' in source
    assert 'group: radar-windows-stable' not in source
