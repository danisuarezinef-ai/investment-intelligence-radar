from datetime import datetime, timezone, timedelta

import radar_core
import radar_learning as rl
import radar_scoring_v2 as sc
import radar_benchmark as rb
import radar_dashboard_v2 as dash
import radar_audit_v15 as audit
import radar_agents as agents
import radar_intelligence as ri


def _tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(radar_core,'DB',str(tmp_path/'radar.db'))
    monkeypatch.setattr(radar_core,'STATUS',str(tmp_path/'status.json'))
    monkeypatch.setattr(radar_core,'LOG',str(tmp_path/'worker.log'))
    monkeypatch.setattr(radar_core,'PID',str(tmp_path/'worker.pid'))
    radar_core.init_db();ri.init_intelligence_db();rl.init_learning_db();agents.ensure_agents()


def _seed(days=130):
    c=radar_core.con();start=datetime.now(timezone.utc)-timedelta(days=days)
    for si,s in enumerate(radar_core.ASSETS):
        p=90+si
        for i in range(days):
            p*=1.002 if (i+si)%9 else 0.996
            c.execute('insert into market_snapshots(ts,symbol,price,volume,source) values(?,?,?,?,?)',((start+timedelta(days=i)).replace(hour=21).isoformat(),s,p,1000000,'test'))
    c.commit();c.close()


def test_multihorizon_scoring_and_369(tmp_path,monkeypatch):
    _tmp(tmp_path,monkeypatch);_seed()
    r=sc.multihorizon_rankings()
    assert set(r)=={'short','medium','long'}
    assert all(r[h] for h in r)
    l=sc.lists_369_v2();assert len(l['high_reliability'])<=3;assert len(l['best_risk_adjusted'])<=6;assert len(l['promising'])<=9


def test_benchmark_agents_returns_five_profiles(tmp_path,monkeypatch):
    _tmp(tmp_path,monkeypatch);_seed();agents.step_all_agents(force=True)
    b=rb.benchmark_agents();assert len(b)==5
    assert all('sharpe' in x and 'benchmark_return_pct' in x for x in b)


def test_integrity_audit_keeps_real_trading_off(tmp_path,monkeypatch):
    _tmp(tmp_path,monkeypatch);_seed(40)
    r=audit.run_integrity_audit();assert r['trading_real'] is False
    assert r['summary']['FAIL']>=0
    assert any(x['test']=='real_trading_off' and x['status']=='PASS' for x in r['tests'])


def test_dashboard_payload_is_read_only_enough_to_render(tmp_path,monkeypatch):
    _tmp(tmp_path,monkeypatch);_seed();rl.detect_regime(True);rl.build_portfolio('1m')
    d=dash.dashboard_payload();assert d['trading_real'] is False
    assert 'model' in d and 'lists_369' in d and 'benchmarks' in d and 'counts' in d
