import json
import os
import zipfile
from pathlib import Path

import pytest

import radar_agents
import radar_forward_ledger_audit_v1 as ledger_audit
import radar_updater_v2 as updater


def _make_update_zip(tmp_path, payload=b'new'):
    pkg=tmp_path/'RadarUpdate.zip'
    with zipfile.ZipFile(pkg,'w') as z:
        for name in updater.PAYLOAD_BINARIES:
            z.writestr(name,payload+b'-'+name.encode())
        z.writestr('RadarUpdater.exe',b'new-updater')
    return pkg


def test_task_6_hot_updater_rolls_back_partial_failure(monkeypatch,tmp_path):
    app=tmp_path/'app';data=tmp_path/'data';app.mkdir();data.mkdir()
    originals={}
    for name in updater.PAYLOAD_BINARIES:
        originals[name]=b'old-'+name.encode();(app/name).write_bytes(originals[name])
    version=app/'version.json';version.write_text(json.dumps({'version':'1.5.19','channel':'stable'}),encoding='utf-8')
    monkeypatch.setattr(updater,'APPDIR',str(app));monkeypatch.setattr(updater,'DATA',str(data));monkeypatch.setattr(updater,'VERSION_FILE',str(version));monkeypatch.setattr(updater,'LOG',str(data/'updater.log'));monkeypatch.setattr(updater,'PID_FILE',str(data/'worker.pid'));monkeypatch.setattr(updater,'stop_processes',lambda:None);monkeypatch.setattr(updater.time,'sleep',lambda *_:None)
    real_copy=updater.shutil.copy2
    def flaky_copy(src,dst,*a,**k):
        if str(src).endswith('RadarSimulationLab.exe') and str(dst).endswith('.new'):
            raise OSError('induced mid-install failure')
        return real_copy(src,dst,*a,**k)
    monkeypatch.setattr(updater.shutil,'copy2',flaky_copy)
    with pytest.raises(OSError,match='induced mid-install failure'):
        updater.install(str(_make_update_zip(tmp_path)),'1.5.20')
    for name,old in originals.items():assert (app/name).read_bytes()==old
    assert json.loads(version.read_text(encoding='utf-8'))['version']=='1.5.19'
    assert 'ROLLBACK_OK' in (data/'updater.log').read_text(encoding='utf-8')


def test_task_6_hot_updater_commits_complete_success(monkeypatch,tmp_path):
    app=tmp_path/'app';data=tmp_path/'data';app.mkdir();data.mkdir()
    for name in updater.PAYLOAD_BINARIES:(app/name).write_bytes(b'old')
    version=app/'version.json';version.write_text(json.dumps({'version':'1.5.19'}),encoding='utf-8')
    monkeypatch.setattr(updater,'APPDIR',str(app));monkeypatch.setattr(updater,'DATA',str(data));monkeypatch.setattr(updater,'VERSION_FILE',str(version));monkeypatch.setattr(updater,'LOG',str(data/'updater.log'));monkeypatch.setattr(updater,'PID_FILE',str(data/'worker.pid'));monkeypatch.setattr(updater,'stop_processes',lambda:None);monkeypatch.setattr(updater.time,'sleep',lambda *_:None)
    updater.install(str(_make_update_zip(tmp_path,b'fresh')),'1.5.20')
    assert json.loads(version.read_text(encoding='utf-8'))['version']=='1.5.20'
    for name in updater.PAYLOAD_BINARIES:assert (app/name).read_bytes().startswith(b'fresh-')


def test_task_7_specialized_paper_agents_exist_and_are_materially_distinct():
    required={'conservative','balanced','aggressive','high_conviction','experimental'}
    assert required.issubset(radar_agents.AGENTS)
    signatures={(v['target_invested'],v['per_position'],v['max_positions'],v['tiers'],v['stop_loss']) for v in radar_agents.AGENTS.values()}
    assert len(signatures)>=5
    assert all(v['initial_cash']>0 for v in radar_agents.AGENTS.values())


def test_task_8_cloud_pc_sync_is_bidirectional_and_version_stamped_at_build():
    sync=Path('radar_pc_sync_hook.py').read_text(encoding='utf-8')
    build=Path('build_windows.ps1').read_text(encoding='utf-8')
    for endpoint in ('/snapshot','/dashboard-v2','/priority-v1','/operational-pipeline-v1','/market-telemetry-v1','/ops-health','/node-heartbeat','/pc-sync'):
        assert endpoint in sync
    assert "origin_node':node_id" in sync and "origin_id':r[0]" in sync
    assert "PC_SYNC_VERSION\\s*=\\s*'[^']+'" in build
    assert "PC_SYNC_VERSION='$version'" in build
    assert "'app_version':PC_SYNC_VERSION" in sync


def test_task_9_restart_authority_has_idempotent_conflict_and_no_backfill_gates():
    persistent=Path('tests/test_persistent_authority_v26.py').read_text(encoding='utf-8')
    for gate in ('test_forward_restore_is_exact_idempotent_and_not_backfill','test_forward_restore_preserves_persisted_mature_outcome','test_forward_authority_conflict_fails_closed'):
        assert gate in persistent
    assert "backfill_used'] is False" in persistent
    assert "reconstructed'] is False" in persistent


def test_task_10_forward_ledger_auditor_passes_clean_records_and_fails_contamination():
    clean={'origin_node':'cloud-primary','origin_id':'1','created_at':'2026-09-10T10:00:00+00:00','symbol':'MSFT','horizon':'1d','target_date':'2026-09-11T10:00:00+00:00','model_version':'v1','prediction_hash':'abc','decision_state':'WAIT','data_cutoff':'2026-09-10T10:00:00+00:00','known_at_boundary':'2026-09-10T10:00:00+00:00','provenance_snapshot':{'lookahead':False}}
    good=ledger_audit.audit_forward_records([clean]);assert good['status']=='PASS' and good['violations']==0 and good['real_trading'] is False
    duplicate=dict(clean);duplicate['payload']={'backfilled':True};duplicate['target_date']='2026-09-09T10:00:00+00:00'
    bad=ledger_audit.audit_forward_records([clean,duplicate])
    assert bad['status']=='FAIL_CLOSED';assert bad['duplicate_authority'];assert bad['duplicate_hash'];assert bad['backfill_contamination'];assert bad['timestamp_errors'];assert bad['repair_performed'] is False


def test_release_is_at_least_v1520():
    version=json.loads(Path('version.json').read_text(encoding='utf-8'))['version']
    assert tuple(map(int,version.split('.'))) >= (1,5,20)
