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
