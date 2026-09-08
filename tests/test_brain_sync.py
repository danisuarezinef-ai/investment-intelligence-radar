import radar_core
import radar_learning_sync as sync
from radar_brain_evolution import Candidate, record_lineage


def test_brain_sync_uses_origin_ids_and_is_incremental(tmp_path,monkeypatch):
    monkeypatch.setattr(radar_core,'DB',str(tmp_path/'radar.db'))
    monkeypatch.setattr(sync,'SYNC_URL','mock://sync');monkeypatch.setattr(sync,'SYNC_TOKEN','test')
    sent=[];monkeypatch.setattr(sync,'_post',lambda payload: sent.append(payload) or {'ok':True})
    record_lineage(Candidate('candidate:x',1,{'a':.1},'champion:1'))
    first=sync.sync_learning_once();second=sync.sync_learning_once()
    assert first['brain_lineages']==1;assert second['brain_lineages']==0
    row=sent[0]['brain_lineages'][0]
    assert row['origin_node']==sync.NODE_ID and row['origin_id']>0 and 'id' not in row
    assert first['brain_vault_registry']==9;assert second['brain_vault_registry']==0
