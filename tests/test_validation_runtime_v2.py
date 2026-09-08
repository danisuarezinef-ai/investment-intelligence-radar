import radar_validation_runtime_v2 as vr


def test_runtime_snapshot_is_read_only_and_fail_closed(monkeypatch):
    monkeypatch.setattr(vr,'shadow_experiment_evidence',lambda:{
      'forward_days':1,'matured_predictions':0,'decisions':0,'max_drawdown_pct':None,
      'brier':None,'hit_rate':None,'excess_return_pct':None,'positive_months':0,
      'ledger_integrity':True,'pit_verified':True,'costs_included':False,'real_trading':False})
    monkeypatch.setattr(vr,'forward_health',lambda:{'started':True,'real_trading':False})
    monkeypatch.setattr(vr,'historical_lab_health',lambda n=8:{'runs':[]})
    out=vr.validation_runtime_snapshot()
    assert out['ready_for_live_review'] is False
    assert out['can_trade'] is False
    assert out['auto_promote'] is False
    assert out['real_trading'] is False
    assert 'costs_included' in out['promotion']['failed']


def test_runtime_snapshot_can_mark_review_ready_but_never_trade(monkeypatch):
    monkeypatch.setattr(vr,'shadow_experiment_evidence',lambda:{
      'forward_days':120,'matured_predictions':150,'decisions':80,'max_drawdown_pct':-6,
      'brier':.16,'hit_rate':.58,'excess_return_pct':4,'positive_months':4,
      'ledger_integrity':True,'pit_verified':True,'costs_included':True,'real_trading':False})
    monkeypatch.setattr(vr,'forward_health',lambda:{'started':True,'real_trading':False})
    monkeypatch.setattr(vr,'historical_lab_health',lambda n=8:{'runs':[]})
    out=vr.validation_runtime_snapshot()
    assert out['ready_for_live_review'] is True
    assert out['can_trade'] is False
    assert out['real_trading'] is False
