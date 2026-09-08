import radar_core
import radar_decision_memory_v2 as dm
import radar_memory_consolidation_v3 as mc


def _tmp(tmp_path,monkeypatch):
    monkeypatch.setattr(radar_core,'DB',str(tmp_path/'radar.db'))
    monkeypatch.setattr(radar_core,'STATUS',str(tmp_path/'status.json'))
    monkeypatch.setattr(radar_core,'LOG',str(tmp_path/'worker.log'))
    monkeypatch.setattr(radar_core,'PID',str(tmp_path/'worker.pid'))
    radar_core.init_db();dm.init_decision_memory_db();mc.init_consolidation_db()


def _episode(i,reward,confidence=.7,action='PAPER_BUY_CANDIDATE'):
    eid=dm.record_episode(agent_id='champion',symbol='MSFT',horizon='1m',regime='risk_on',state={'i':i},evidence={},hypothesis={},action=action,confidence=confidence,tags=['champion'])
    dm.evaluate_episode(eid,{'reward':reward,'hit':reward>0})
    return eid


def test_consolidation_builds_shrunk_reliable_patterns(tmp_path,monkeypatch):
    _tmp(tmp_path,monkeypatch)
    for i in range(12):_episode(i,2.0 if i<9 else -1.0,.75)
    out=mc.consolidate_memory();prior=mc.pattern_prior(agent_id='champion',action='PAPER_BUY_CANDIDATE',horizon='1m',regime='risk_on',symbol='MSFT')
    assert out['episodes_used']==12
    assert out['patterns']>=4
    assert prior['available'] is True
    assert prior['reliability']>0
    assert .5<prior['hit_rate']<1.0
    assert 0<prior['expected_reward']<2.0
    assert prior['effective_n']>=12
    assert prior['real_trading'] is False


def test_sparse_pattern_is_ignored_by_default_prior(tmp_path,monkeypatch):
    _tmp(tmp_path,monkeypatch);_episode(1,-5.0,.95);mc.consolidate_memory()
    prior=mc.pattern_prior(agent_id='champion',action='PAPER_BUY_CANDIDATE',horizon='1m',regime='risk_on',symbol='MSFT',min_n=2)
    assert prior['available'] is False
    assert prior['expected_reward']==0.0


def test_consolidation_is_rebuildable_not_additive(tmp_path,monkeypatch):
    _tmp(tmp_path,monkeypatch)
    for i in range(4):_episode(i,1.0,.6)
    first=mc.consolidate_memory();second=mc.consolidate_memory()
    assert first['patterns']==second['patterns']
    c=radar_core.con();n=c.execute('select count(*) from decision_memory_patterns').fetchone()[0];c.close()
    assert n==second['patterns']
