import radar_paper_reconciliation_racefix_v1 as fix


def _snapshots():
    cp={'state_hash':'persisted-hash','observed_at':'2026-09-15T11:00:00Z','tables':{
        'champion_paper_marks':[{'cash':100.0,'total':101.0}],
        'paper_agent_positions':[],'champion_paper_positions':[]}}
    core={'completed_cycles':355,'generation':7,'completed_experiments':2,'last_cycle_at':'a','last_research_at':'b'}
    return cp,core


def test_identity_uses_persisted_snapshot_not_later_mutable_state(monkeypatch):
    cp,core=_snapshots()
    monkeypatch.setattr(fix.v12,'_positions_hash',lambda a,b:'positions')
    monkeypatch.setattr(fix.v12,'_canon_hash',lambda x:'learning')
    local=fix._identity_from_snapshots(cp,core,'session-1')
    # Simulate a worker committing a newer SQLite generation immediately after persist.
    cp['state_hash']='newer-live-hash'
    cp['tables']['champion_paper_marks'][-1]['total']=102.0
    assert local['state_hash']=='persisted-hash'
    assert local['equity']=='101.0000000000'
    assert local['cycle']==355
    assert local['session_id']=='session-1'
    assert local['real_trading'] is False


def test_remote_identity_matches_persisted_generation(monkeypatch):
    monkeypatch.setattr(fix.v12,'_positions_hash',lambda a,b:'positions')
    monkeypatch.setattr(fix.v12,'_canon_hash',lambda x:'learning')
    evidence={'ok':True,'checkpoint':{'state_hash':'persisted-hash','champion_cash':100,'champion_total':101,
              'paper_positions':[],'champion_positions':[],'observed_at':'2026-09-15T11:00:00Z'},
              'autonomy':{'payload':{'completed_cycles':355}},'lease':{'session_id':'session-1'}}
    remote=fix._remote_identity(evidence)
    assert remote['state_hash']=='persisted-hash'
    assert remote['cycle']==355
    assert remote['real_trading'] is False


def test_persisted_generation_reconciles_even_if_live_state_advances(monkeypatch):
    cp,core=_snapshots()
    monkeypatch.setattr(fix.v12,'_positions_hash',lambda a,b:'positions')
    monkeypatch.setattr(fix.v12,'_canon_hash',lambda x:'learning')
    local=fix._identity_from_snapshots(cp,core,'session-1')
    evidence={'ok':True,'checkpoint':{'state_hash':'persisted-hash','champion_cash':100,'champion_total':101,
              'paper_positions':[],'champion_positions':[],'observed_at':'2026-09-15T11:00:00Z'},
              'autonomy':{'payload':core.copy()},'lease':{'session_id':'session-1'}}
    remote=fix._remote_identity(evidence)
    cp['state_hash']='N+1-live-hash'; core['completed_cycles']=356
    rec=fix.v12.tasks2130.hard.persistence_reconciliation_gate(local,remote)
    assert rec['status']=='RECONCILED'


def test_real_persisted_divergence_remains_fail_closed(monkeypatch):
    cp,core=_snapshots()
    monkeypatch.setattr(fix.v12,'_positions_hash',lambda a,b:'positions')
    monkeypatch.setattr(fix.v12,'_canon_hash',lambda x:'learning')
    local=fix._identity_from_snapshots(cp,core,'session-1')
    evidence={'ok':True,'checkpoint':{'state_hash':'different-durable-hash','champion_cash':100,'champion_total':101,
              'paper_positions':[],'champion_positions':[],'observed_at':'2026-09-15T11:00:00Z'},
              'autonomy':{'payload':core.copy()},'lease':{'session_id':'session-1'}}
    remote=fix._remote_identity(evidence)
    rec=fix.v12.tasks2130.hard.persistence_reconciliation_gate(local,remote)
    assert rec['status']!='RECONCILED'
    assert rec.get('real_trading') is False
    assert 'state_hash' in (rec.get('mismatched_fields') or [])


def test_install_replaces_only_v12_durable_reconciliation_owner(monkeypatch):
    old=fix.v12._durable_sync_once
    try:
        out=fix.install()
        assert fix.v12._durable_sync_once is fix.durable_sync_once
        assert out['owner']=='cloud_service_v12._durable_sync_once'
        assert out['real_trading'] is False
    finally:
        fix.v12._durable_sync_once=old
