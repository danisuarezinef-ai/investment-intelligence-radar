from radar_forward_autonomy_v1 import run_forward_cycle
from radar_global_universe_v3 import build_global_funnel
from radar_valuation_engine_v1 import valuation_card
from radar_portfolio_optimizer_v3 import optimize_capital
from radar_evidence_scorecard_v1 import scorecard
from radar_champion_challenger_v1 import compete
from radar_live_readiness_v2 import evaluate
from radar_cloud_contract_v4 import audit_contract
from radar_priority_runtime_v1 import priority_snapshot

def test_forward_cycle_freezes_before_outcome_and_never_trades():
    frozen=[]
    x=run_forward_cycle(observe=lambda:{'px':1},discover=lambda o:[{'symbol':'X'}],decide=lambda o:{'symbol':'X'},freeze=frozen.append)
    assert x['receipt']['decision_frozen'] is True and frozen
    assert x['receipt']['outcome_known_at_decision'] is False and x['execution']['allowed'] is False

def test_universe_funnel_does_not_claim_unseen_global_coverage():
    x=build_global_funnel([{'symbol':'A','liquidity_score':1,'data_quality':1,'momentum_score':1}])
    assert x['universe_count']==1 and x['global_coverage_claim']=='OBSERVED_INPUT_ONLY'

def test_valuation_missing_evidence_fails_closed():
    x=valuation_card('A',{'price':10})
    assert x['evidence_complete'] is False and x['valuation_score'] is None

def test_optimizer_requires_drawdown_and_keeps_live_off():
    x=optimize_capital(cash=100,equity=100,opportunities=[])
    assert x['status']=='BLOCKED' and x['real_trading'] is False

def test_scorecard_rejects_backfill_and_requires_sample():
    rows=[{'matured':True,'backfilled':True,'net_return':9,'excess_return':8}]
    x=scorecard(rows,min_decisions=1)
    assert x['matured_decisions']==0 and x['performance_verified'] is False

def test_scorecard_missing_cost_or_benchmark_evidence_fails_closed():
    rows=[{'matured':True,'backfilled':False,'return_pct':5.0} for _ in range(30)]
    x=scorecard(rows,min_decisions=30)
    assert x['matured_decisions']==30
    assert x['net_return_observations']==0 and x['excess_return_observations']==0
    assert x['mean_net_return'] is None and x['mean_excess_return'] is None
    assert x['benchmark_and_cost_evidence_complete'] is False
    assert x['status']=='INSUFFICIENT_EVIDENCE' and x['performance_verified'] is False

def test_scorecard_requires_both_net_and_excess_sample():
    rows=[{'matured':True,'backfilled':False,'net_return':.01} for _ in range(30)]
    x=scorecard(rows,min_decisions=30)
    assert x['net_return_observations']==30 and x['excess_return_observations']==0
    assert x['performance_verified'] is False

def test_challenger_never_auto_replaces():
    x=compete([{'name':'a','forward_n':50,'mean_excess_return':.03},{'name':'b','forward_n':50,'mean_excess_return':.01}],min_forward_n=40)
    assert x['automatic_replacement'] is False and x['weights_applied_automatically'] is False

def test_tiny_live_gate_never_enables_execution():
    m={'days':999,'decisions':999,'max_drawdown':-.01,'benchmark_coverage':1,'cost_coverage':1,'positive_months':12,'degradation_clear':True,'performance_verified':True}
    x=evaluate(m,human_approved=True)
    assert x['ready_for_tiny_live_review'] is True and x['live_execution_allowed'] is False and x['real_trading'] is False

def test_cloud_contract_marks_unverified_endpoint():
    x=audit_contract({'/health':200},{})
    assert '/node-heartbeat' in x['endpoint_failures'] and x['status']!='HEALTHY'

def test_priority_snapshot_is_read_only():
    x=priority_snapshot(account={'equity':100,'cash':100,'invested':0},decision=None,opportunities=[],forward_records=[],models=[],endpoint_status={},freshness={},promotion_metrics={})
    assert x['can_trade'] is False and x['real_trading'] is False and x['strategy_performance_verified'] is False
