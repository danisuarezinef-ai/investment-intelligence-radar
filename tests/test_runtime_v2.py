import radar_runtime_v2 as r

def test_runtime_real_trading_disabled():
    assert r.REAL_TRADING is False
    assert r.runtime_snapshot()['real_trading'] is False

def test_runtime_fast_cycle_is_fail_soft():
    out=r.safe_fast_cycle()
    assert isinstance(out,dict)
    assert out['real_trading'] is False
    assert 'ok' in out

def test_runtime_deep_cycle_is_fail_soft():
    out=r.safe_deep_cycle()
    assert isinstance(out,dict)
    assert out['real_trading'] is False
    assert 'ok' in out

def test_runtime_deep_cycle_detects_and_propagates_regime(monkeypatch):
    seen={}
    monkeypatch.setattr(r,'detect_regime',lambda store=True:{'regime':'risk_off','confidence':.8})
    def fake(regime='unknown'):
        seen['regime']=regime
        return {'learning':{},'real_trading':False}
    monkeypatch.setattr(r,'deep_learning_cycle',fake)
    out=r.safe_deep_cycle()
    assert out['ok'] is True
    assert out['regime']=='risk_off'
    assert seen['regime']=='risk_off'
    assert out['regime_detection']['confidence']==.8
