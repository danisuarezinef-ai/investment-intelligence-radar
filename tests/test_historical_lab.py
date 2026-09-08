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
            drift=.0015 + (si%4)*.00015
            shock=-.012 if (i+si)%29==0 else (.006 if (i+2*si)%17==0 else 0)
            p*=1+drift+shock
            c.execute('insert into market_snapshots(ts,symbol,price,volume,source) values(?,?,?,?,?)',((start+timedelta(days=i)).replace(hour=21).isoformat(),s,p,1000000+si*1000,'test-historical'))
    c.commit();c.close()


def test_historical_observations_are_cutoff_provenanced(tmp_path,monkeypatch):
    _tmp(tmp_path,monkeypatch);_seed();obs=hl.build_historical_observations();assert len(obs)>500
    x=obs[0];assert x['provenance']['lookahead'] is False;assert x['provenance']['future_date']>x['provenance']['cutoff']
    assert set(x['features'])=={'momentum7','momentum30','momentum90','volatility','source_quality','regime_fit','causal_strength'}

def test_purge_embargo_removes_overlapping_labels(tmp_path,monkeypatch):
    _tmp(tmp_path,monkeypatch);_seed();obs=hl.build_historical_observations();dates=sorted({x['ts'] for x in obs});boundary=dates[130]
    train,valid=hl.purged_temporal_split(obs,set(dates[:130]),set(dates[130:140]),1)
    assert valid;assert train;assert all(x['provenance']['future_date']<boundary for x in train)


def test_evolutionary_walk_forward_has_vault_and_final_test(tmp_path,monkeypatch):
    _tmp(tmp_path,monkeypatch);_seed();r=hl.run_historical_lab(promote=False)
    assert r['observations']>500;assert r['folds']>=hl.MIN_FOLDS;assert r['vault_n']>0;assert r['test_n']>0
    assert r['challengers']==len(hl.CHALLENGER_VARIANTS);assert r['selected_challenger'] in {x[0] for x in hl.CHALLENGER_VARIANTS};assert r['promoted'] is False
    health=hl.historical_lab_health();m=health['runs'][0]['metadata']
    assert m['lookahead'] is False;assert m['vault_untouched_during_evolution'] is True;assert m['test_untouched_until_selection'] is True
    assert m['vault_not_used_for_candidate_selection'] is True
    assert health['guardrails']['temporal_vault'] is True


def test_challenger_population_is_persisted(tmp_path,monkeypatch):
    _tmp(tmp_path,monkeypatch);_seed();r=hl.run_historical_lab(promote=False);c=radar_core.con()
    rows=c.execute('select challenger_name,selected from historical_challenger_results where run_id=?',(r['run_id'],)).fetchall();c.close()
    assert len(rows)==len(hl.CHALLENGER_VARIANTS);assert sum(int(x[1]) for x in rows)==1


def test_historical_lab_never_enables_real_trading(tmp_path,monkeypatch):
    _tmp(tmp_path,monkeypatch);_seed();r=hl.run_historical_lab(promote=False);assert r['trading_real'] is False
