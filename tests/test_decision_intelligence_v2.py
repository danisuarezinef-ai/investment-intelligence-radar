from radar_decision_intelligence import *
from radar_portfolio_intelligence import target_weights
from radar_thesis_intelligence import Thesis,evaluate_thesis
from radar_discovery_intelligence import investable_discovery,surprise

def test_disagreement_can_force_wait():
    u=Uncertainty(.9,.9,.9,.1,.1)
    assert decide('X','1m',10,2,.1,u).action=='WAIT'

def test_good_forecast_can_lose_to_better_alternative():
    u=Uncertainty(.9,.05,.95,.05,.05)
    d=decide('X','1m',4,1,.1,u,alternative_return=6)
    assert d.action!='BUY'

def test_master_score_penalizes_drawdown():
    base={'risk_adjusted_return':.8,'cagr':.8,'sortino':.8,'calibration':.8,'hit_rate':.8,'stability':.8,'tail_resilience':.8,'cost_efficiency':.8,'regime_robustness':.8,'abstention_quality':.8}
    assert master_investor_score({**base,'drawdown_severity':.1})>master_investor_score({**base,'drawdown_severity':.9})

def test_portfolio_keeps_cash_and_caps_position():
    p=target_weights([{'symbol':'A','score':5,'confidence':.9,'sector':'tech'},{'symbol':'B','score':1,'confidence':.5,'sector':'tech'}],max_position=.15)
    assert max(p['weights'].values())<=.15 and p['cash']>=.10 and p['real_trading'] is False

def test_kill_criterion_is_explicit():
    t=Thesis('A','1m','growth',kill_if=['license revoked'])
    assert evaluate_thesis(t,['Regulator: license revoked'])['state']=='INVALIDATED'

def test_priced_in_destroys_discovery_value():
    assert investable_discovery(1,1,.9,1,1)<investable_discovery(1,1,.1,1,1)

def test_surprise_uses_expectation():
    assert surprise(120,100,10)==2

def test_real_trading_off():
    assert REAL_TRADING is False
