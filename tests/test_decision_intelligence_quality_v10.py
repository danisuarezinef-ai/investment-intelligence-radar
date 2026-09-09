import radar_expected_return_v1 as er
import radar_cost_model as costs
import radar_universe_pit as pit
import radar_causal_scoring_v2 as causal

def test_expected_return_does_not_turn_uncalibrated_score_into_optimizer_input(monkeypatch):
    monkeypatch.setattr(er,'forward_calibration',lambda symbol=None,horizon='1m':{'n':0,'excess_n':0,'mean_excess_return_pct':None})
    x=er.expected_return_signal({'symbol':'MSFT','score':80},'1m')
    assert x['expected_return'] is None
    assert x['research_proxy'] is not None
    assert x['optimizer_eligible'] is False

def test_forward_expected_return_requires_benchmark_excess_evidence(monkeypatch):
    monkeypatch.setattr(er,'forward_calibration',lambda symbol=None,horizon='1m':{'n':30,'excess_n':0,'mean_excess_return_pct':None})
    assert er.expected_return_signal({'symbol':'MSFT','score':80})['optimizer_eligible'] is False

def test_verified_forward_expected_return_is_explicit(monkeypatch):
    monkeypatch.setattr(er,'forward_calibration',lambda symbol=None,horizon='1m':{'n':30,'excess_n':30,'mean_excess_return_pct':2.0})
    x=er.expected_return_signal({'symbol':'MSFT','score':80})
    assert x['status']=='VERIFIED_FORWARD'
    assert x['expected_return']==0.02
    assert x['optimizer_eligible'] is True

def test_risk_signal_requires_observed_inputs():
    assert er.risk_signal({'symbol':'X'})['optimizer_eligible'] is False
    assert er.risk_signal({'symbol':'X','risk':'bajo','base':{'volatility':10}})['risk_score'] is not None

def test_survivorship_unknown_fails_visible():
    x=pit.survivorship_audit(['NONEXISTENT_TEST_SYMBOL'],'2001-01-01T00:00:00+00:00')
    assert x['survivorship_bias_risk'] is True

def test_cost_model_is_assumption_not_broker_claim():
    x=costs.estimate_cost(10000,fx_bps=3)
    assert x['total']>0 and x['verified_broker_costs'] is False and x['real_trading'] is False

def test_causal_unknown_is_neutral(monkeypatch):
    class C:
        def execute(self,*a,**k):return self
        def fetchall(self):return []
        def close(self):pass
    monkeypatch.setattr(causal,'init_db',lambda:None);monkeypatch.setattr(causal,'init_learning_db',lambda:None);monkeypatch.setattr(causal,'con',lambda:C())
    x=causal.causal_symbol_score('X');assert x['available'] is False and x['adjustment']==0
