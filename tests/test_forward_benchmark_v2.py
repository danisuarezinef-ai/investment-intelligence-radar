import json
import radar_core
import radar_forward_benchmark_v2 as fb


def _tmp(tmp_path,monkeypatch):
    monkeypatch.setattr(radar_core,'DB',str(tmp_path/'radar.db'));radar_core.init_db()
    c=radar_core.con()
    for j,s in enumerate(list(radar_core.ASSETS)[:8]):
        c.execute('insert into market_snapshots(ts,symbol,price,volume,source) values(?,?,?,?,?)',('2026-01-01T10:00:00+00:00',s,100+j,None,'TEST'))
        c.execute('insert into market_snapshots(ts,symbol,price,volume,source) values(?,?,?,?,?)',('2026-01-03T10:00:00+00:00',s,(100+j)*1.10,None,'TEST'))
    c.commit();c.close()


def test_same_window_equal_weight_benchmark(tmp_path,monkeypatch):
    _tmp(tmp_path,monkeypatch)
    r=fb.equal_weight_benchmark('2026-01-01T12:00:00+00:00','2026-01-03T00:00:00+00:00')
    assert r['available'] is True
    assert r['constituents']==8
    assert abs(r['return_pct']-10)<1e-9
    assert r['real_trading'] is False


def test_benchmark_fails_closed_with_too_few_constituents(tmp_path,monkeypatch):
    monkeypatch.setattr(radar_core,'DB',str(tmp_path/'radar.db'));radar_core.init_db()
    r=fb.equal_weight_benchmark('2026-01-01','2026-01-03')
    assert r['available'] is False
    assert r['return_pct'] is None


def test_costs_are_never_assumed():
    r=fb.explicit_cost_evidence('{}','{}')
    assert r['available'] is False
    assert r['costs_pct'] is None


def test_explicit_costs_enable_net_and_excess(tmp_path,monkeypatch):
    _tmp(tmp_path,monkeypatch)
    rec={'created_at':'2026-01-01T12:00:00+00:00','target_date':'2026-01-03T00:00:00+00:00','return_pct':12,'payload':json.dumps({'costs_pct':1}),'outcome':'{}'}
    r=fb.benchmarked_forward_record(rec)
    assert r['net_return_pct']==11
    assert abs(r['excess_return_pct']-1)<1e-9
    assert r['fully_attributable'] is True
    assert r['real_trading'] is False
