from datetime import datetime, timezone, timedelta

import radar_core
import radar_learning as rl
import radar_historical_lab as hl


def _tmp(tmp_path,monkeypatch):
    monkeypatch.setattr(radar_core,'DB',str(tmp_path/'radar.db'))
    monkeypatch.setattr(radar_core,'STATUS',str(tmp_path/'status.json'))
    monkeypatch.setattr(radar_core,'LOG',str(tmp_path/'worker.log'))
    monkeypatch.setattr(radar_core,'PID',str(tmp_path/'worker.pid'))
    radar_core.init_db();rl.init_learning_db();hl.init_historical_lab_db()


def _seed(days=280):
    c=radar_core.con();start=datetime.now(timezone.utc)-timedelta(days=days)
    for si,s in enumerate(radar_core.ASSETS):
        p=70+si*3
        for i in range(days):
            # deterministic but heterogeneous path with trend and pullbacks
            drift=.0015 + (si%4)*.00015
            shock=-.012 if (i+si)%29==0 else (.006 if (i+2*si)%17==0 else 0)
            p*=1+drift+shock
            c.execute('insert into market_snapshots(ts,symbol,price,volume,source) values(?,?,?,?,?)',((start+timedelta(days=i)).replace(hour=21).isoformat(),s,p,1000000+si*1000,'test-historical'))
    c.commit();c.close()


def test_historical_observations_are_cutoff_provenanced(tmp_path,monkeypatch):
    _tmp(tmp_path,monkeypatch);_seed()
    obs=hl.build_historical_observations()
    assert len(obs)>500
    x=obs[0]
    assert x['provenance']['lookahead'] is not True if 'lookahead' in x['provenance'] else True
    assert x['provenance']['future_date']>x['provenance']['cutoff']
    assert set(x['features'])=={'momentum7','momentum30','momentum90','volatility','source_quality','regime_fit','causal_strength'}


def test_walk_forward_lab_records_untouched_test(tmp_path,monkeypatch):
    _tmp(tmp_path,monkeypatch);_seed()
    r=hl.run_historical_lab(promote=False)
    assert r['observations']>500
    assert r['folds']>=hl.MIN_FOLDS
    assert r['test_n']>0
    assert r['promoted'] is False
    health=hl.historical_lab_health()
    assert health['runs'][0]['metadata']['lookahead'] is False
    assert health['guardrails']['final_test_untouched'] is True


def test_historical_lab_never_enables_real_trading(tmp_path,monkeypatch):
    _tmp(tmp_path,monkeypatch);_seed()
    r=hl.run_historical_lab(promote=False)
    assert r['trading_real'] is False
