import pytest
from radar_performance_forward_v1 import forward_performance
from radar_promotion_dashboard_v1 import promotion_dashboard
from radar_paper_account_v5 import append_event,rebuild_account
from radar_simulator_stack_v4 import run_simulator_cycle
from radar_decision_capital_view_v1 import decision_capital_view

def test_forward_missing_benchmark_and_cost_not_zero():
    out=forward_performance([{'matured':True,'backfilled':False,'return_pct':5.0}])
    assert out['gross_return_mean_pct']==5.0
    assert out['net_return_mean_pct'] is None
    assert out['excess_return_mean_pct'] is None
    assert out['benchmark_coverage']==0.0 and out['cost_coverage']==0.0

def test_backfill_forbidden_and_account_rebuild():
    with pytest.raises(ValueError): append_event([],{'type':'BUY','backfilled':True})
    events=[{'type':'BUY','symbol':'MSFT','qty':2,'price':100,'fees':1,'backfilled':False},
            {'type':'SELL','symbol':'MSFT','qty':1,'price':110,'fees':1,'backfilled':False}]
    out=rebuild_account(events,1000)
    assert out['cash']==908
    assert out['positions']['MSFT']['qty']==1
    assert out['real_trading'] is False

def test_position_underflow_blocks():
    with pytest.raises(ValueError): rebuild_account([{'type':'SELL','symbol':'MSFT','qty':1,'price':100,'backfilled':False}],1000)

def test_promotion_dashboard_reports_first_missing_gate():
    p=promotion_dashboard({}, {}, {})
    assert p['next_required_gate']=='shadow_to_paper_gate'
    assert p['live_execution_allowed'] is False and p['real_trading'] is False

def test_simulator_fallback_is_explicit_and_never_live():
    portfolio={'total':1000,'invested':0,'cash':1000,'positions':[],'max_drawdown_pct':0}
    out=run_simulator_cycle([],portfolio,heuristic_fallback=[{'symbol':'MSFT','action':'BUY'}])
    assert out['mode']=='SIMULATION_ONLY_HEURISTIC'
    assert out['simulated_decisions'][0]['simulation_only'] is True
    assert out['real_trading'] is False

def test_decision_view_labels_unverified_performance():
    v=decision_capital_view({'total':1000,'cash':1000,'invested':0},[],{}, {})
    assert v['labels']['performance']=='NOT VERIFIED'
    assert v['live_execution_allowed'] is False
