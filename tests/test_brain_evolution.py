import radar_core
import radar_brain_evolution as be


def setup(tmp_path,monkeypatch):
    monkeypatch.setattr(radar_core,'DB',str(tmp_path/'radar.db'));radar_core.init_db();be.init_brain_db()


def test_live_evidence_has_highest_weight(tmp_path,monkeypatch):
    setup(tmp_path,monkeypatch)
    assert be.EPISTEMIC_WEIGHTS['live_forward']>be.EPISTEMIC_WEIGHTS['historical_final_test']>be.EPISTEMIC_WEIGHTS['historical_vault']


def test_seed_population_is_diverse_and_bounded(tmp_path,monkeypatch):
    setup(tmp_path,monkeypatch);w={'a':.2,'b':.1,'c':-.1,'d':.05};p=be.seed_population('2.0.0',w,['risk_on','risk_off'])
    assert len(p)==be.POPULATION;assert len({tuple(sorted(x.weights.items())) for x in p})>5
    for x in p:assert sum(abs(x.weights[k]-w[k]) for k in w)<=be.MAX_TOTAL_DISTANCE+1e-9


def test_historical_only_never_promotes_live(tmp_path,monkeypatch):
    setup(tmp_path,monkeypatch);be.record_evidence('x','historical_walk_forward','mixed','1m',100,.2);be.record_evidence('x','historical_vault','mixed','1m',50,.18);be.record_evidence('x','historical_final_test','mixed','1m',50,.17)
    g=be.promotion_gate('x');assert g['shadow_eligible'];assert not g['promotion_eligible'];assert g['real_trading'] is False


def test_live_can_unlock_promotion_gate(tmp_path,monkeypatch):
    setup(tmp_path,monkeypatch);be.record_evidence('x','historical_walk_forward','mixed','1m',100,.2);be.record_evidence('x','historical_vault','mixed','1m',50,.18);be.record_evidence('x','historical_final_test','mixed','1m',100,.2);be.record_evidence('x','live_forward','mixed','1m',50,.12)
    g=be.promotion_gate('x');assert g['promotion_eligible'];assert g['real_trading'] is False


def test_anti_overfit_penalizes_instability():
    stable=be.anti_overfit_score([.1,.11,.09,.1],7,{'a':.1,'b':.1});unstable=be.anti_overfit_score([.4,-.2,.35,-.15],7,{'a':.4,'b':-.2});assert stable['score']>unstable['score']

def test_shadow_prediction_is_frozen_and_outcome_immutable(tmp_path,monkeypatch):
    setup(tmp_path,monkeypatch);key=be.freeze_shadow_prediction('x','MSFT','1w','2026-01-01','2026-01-08',.4,.7,{}, {'lookahead':False},'p1');be.evaluate_shadow_prediction(key,.05)
    import pytest
    with pytest.raises(ValueError):be.evaluate_shadow_prediction(key,.10)

def test_vault_guards_and_reuse_penalty(tmp_path,monkeypatch):
    setup(tmp_path,monkeypatch)
    import pytest
    with pytest.raises(ValueError):be.open_vault('gfc','x','training')
    with pytest.raises(PermissionError):be.open_vault('deep_final_test','x','final_test')
    assert be.open_vault('gfc','x','validation')['reuse_penalty']==0
    assert be.open_vault('gfc','y','validation')['reuse_penalty']>0

def test_correlated_family_votes_are_compressed():
    r=be.ensemble_consensus([{'lineage':'a','family':'trend','score':1},{'lineage':'b','family':'trend','score':1},{'lineage':'c','family':'risk','score':-1}])
    assert r['independent_families']==2;assert abs(r['score'])<.01;assert r['abstain']
