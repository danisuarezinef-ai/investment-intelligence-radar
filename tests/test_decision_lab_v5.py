import radar_decision_lab_v5 as v5


def test_new_capital_is_blocked_when_valuation_or_cost_evidence_missing():
    c=v5.decision_card(symbol='MSFT',horizon='1m',model_score=20,confidence=.8,
      returns=[2,3,1,4,2],valuation_risk=None,cost_pct=None,holding=False)
    assert c.action=='WATCH'
    assert c.evidence_complete is False
    assert 'valuation_risk_missing' in c.blockers
    assert 'cost_evidence_missing' in c.blockers
    assert c.real_trading is False


def test_existing_holding_can_reduce_on_negative_score_with_incomplete_evidence():
    c=v5.decision_card(symbol='MSFT',horizon='1m',model_score=-20,confidence=.8,
      returns=[-2,-3,-1,-4,-2],valuation_risk=None,cost_pct=None,holding=True)
    assert c.action=='REDUCE'
    assert c.real_trading is False


def test_complete_strong_evidence_can_buy_but_never_trade():
    c=v5.decision_card(symbol='MSFT',horizon='1m',model_score=30,confidence=.9,
      returns=[12,14,11,13,15,10],valuation_risk=1.0,cost_pct=.1,holding=False,
      alternative_symbol='NVDA',alternative_expected_return_pct=2.0)
    assert c.evidence_complete is True
    assert c.action=='BUY'
    assert c.alternative_symbol=='NVDA'
    assert c.real_trading is False


def test_complete_negative_nonholding_is_avoid_or_watch_not_reduce():
    c=v5.decision_card(symbol='MSFT',horizon='1m',model_score=-30,confidence=.9,
      returns=[-8,-6,-9,-7,-10,-5],valuation_risk=2.0,cost_pct=.1,holding=False)
    assert c.action in ('AVOID','WATCH')
    assert c.action!='REDUCE'


def test_empirical_distribution_preserves_upside_downside():
    d=v5.empirical_distribution([-10,-5,0,5,20])
    assert d['n']==5
    assert d['mean']==2
    assert d['downside_pct']<d['upside_pct']


def test_runtime_snapshot_is_fail_closed_and_uses_current_cards(monkeypatch):
    monkeypatch.setattr(v5,'_latest_predictions',lambda:[{'id':1,'symbol':'MSFT','horizon':'1m','score':25,'confidence':.8,'created_at':'x'}])
    monkeypatch.setattr(v5,'_returns',lambda s,h:[2,3,1,4,2])
    monkeypatch.setattr(v5,'_holdings',lambda:set())
    out=v5.decision_lab_v5_snapshot()
    assert out['version']=='v5'
    assert out['cards'][0]['action']=='WATCH'
    assert out['buy_blocked_without_complete_evidence'] is True
    assert out['can_trade'] is False
    assert out['real_trading'] is False
