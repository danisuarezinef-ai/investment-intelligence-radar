from datetime import datetime, timezone, timedelta
import json

import radar_core
import radar_learning as rl
import radar_causal as rc


def _tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(radar_core, 'DB', str(tmp_path/'radar.db'))
    monkeypatch.setattr(radar_core, 'STATUS', str(tmp_path/'status.json'))
    monkeypatch.setattr(radar_core, 'LOG', str(tmp_path/'worker.log'))
    monkeypatch.setattr(radar_core, 'PID', str(tmp_path/'worker.pid'))
    radar_core.init_db(); rl.init_learning_db()


def _seed_prices(days=120):
    c=radar_core.con(); start=datetime.now(timezone.utc)-timedelta(days=days)
    for sym_i,sym in enumerate(radar_core.ASSETS):
        p=100+sym_i
        for i in range(days):
            p*=1.0015 if (i+sym_i)%7 else 0.997
            c.execute('insert into market_snapshots(ts,symbol,price,volume,source) values(?,?,?,?,?)',((start+timedelta(days=i)).replace(hour=21).isoformat(),sym,p,1000000,'test'))
    c.commit();c.close()


def test_learning_schema_and_regime(tmp_path, monkeypatch):
    _tmp(tmp_path,monkeypatch);_seed_prices(80)
    m=rl.active_model();assert m['version']=='2.0.0'
    r=rl.detect_regime(True);assert r['regime'] in {'risk_on_growth','risk_off','defensive_rotation','mixed'}
    assert rl.audit_system()


def test_point_in_time_backtest_uses_past_window(tmp_path, monkeypatch):
    _tmp(tmp_path,monkeypatch);_seed_prices(140)
    out=rl.backtest_point_in_time(symbols=['MSFT'],lookback=20,forward=5)
    assert out and out[0]['observations']>20
    assert 0<=out[0]['hit_rate']<=1


def test_learning_guardrail_requires_observations(tmp_path, monkeypatch):
    _tmp(tmp_path,monkeypatch)
    result=rl.learn_if_ready(min_observations=10)
    assert result['accepted'] is False
    assert result['reason']=='insufficient_observations'


def test_causal_graph_builds_second_order_edges(tmp_path, monkeypatch):
    _tmp(tmp_path,monkeypatch)
    c=radar_core.con();c.execute('insert into information_events(ts,source,title,url,category) values(?,?,?,?,?)',(radar_core.now(),'test','Nvidia AI GPU demand increases data center power','https://example.test/1','technology'));c.commit();c.close()
    n=rc.build_causal_graph(168);assert n>0
    g=rc.graph_summary();assert g['edges']>0
    s=rc.symbol_causal_summary('NVDA');assert s['inbound'] or s['outbound']
