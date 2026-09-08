import radar_core
import radar_brain_vaults as v
from radar_brain_ensemble import ensemble_prediction


def setup(tmp_path,monkeypatch):
    monkeypatch.setattr(radar_core,'DB',str(tmp_path/'r.db'));radar_core.init_db();v.ensure_vaults()


def test_rotating_vault_retires_after_peeks(tmp_path,monkeypatch):
    setup(tmp_path,monkeypatch);x=v.next_vault();assert x
    assert v.open_vault(x['key'],'test1')['status']=='sealed'
    v.open_vault(x['key'],'test2');assert v.open_vault(x['key'],'test3')['status']=='retired'


def test_gauntlet_penalizes_regime_failure():
    robust=v.regime_gauntlet_score([{'objective':.12},{'objective':.11},{'objective':.10}])
    brittle=v.regime_gauntlet_score([{'objective':.30},{'objective':.25},{'objective':-.20}]);assert robust['score']>brittle['score']


def test_ensemble_disagreement_reduces_confidence():
    common={'confidence':.8,'regime_score':.8,'transfer_score':.4,'status':'shadow'}
    agree=ensemble_prediction([dict(common,lineage='a',score=70),dict(common,lineage='b',score=72)])
    disagree=ensemble_prediction([dict(common,lineage='a',score=20),dict(common,lineage='b',score=90)])
    assert agree['confidence']>disagree['confidence'];assert agree['uncertainty']<disagree['uncertainty']
