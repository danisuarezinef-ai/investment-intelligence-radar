import pytest

import cloud_service_v8 as v8
import radar_supabase_sync_partitioned_v2 as ps


def test_partition_family_advances_cursor_only_after_every_chunk_success(monkeypatch):
    sent=[];cursors=[]
    monkeypatch.setattr(ps.base,'_post',lambda payload,timeout=None: sent.append(payload) or {'ok':True})
    monkeypatch.setattr(ps.base,'_control_set',lambda key,value:cursors.append((key,value)))
    rows=[{'id':i} for i in range(5)]
    ps._send_family('events','information_events',rows,cursor_key='cursor',cursor_value=5,chunk_size=2)
    assert [len(x['information_events']) for x in sent]==[2,2,1]
    assert cursors==[('cursor',5)]


def test_partition_family_failure_keeps_cursor_for_exact_retry_window(monkeypatch):
    calls={'n':0};cursors=[]
    def post(payload,timeout=None):
        calls['n']+=1
        if calls['n']==2:raise TimeoutError('partition')
        return {'ok':True}
    monkeypatch.setattr(ps.base,'_post',post)
    monkeypatch.setattr(ps.base,'_control_set',lambda key,value:cursors.append((key,value)))
    with pytest.raises(TimeoutError):
        ps._send_family('marks','portfolio_values',[{'id':i} for i in range(5)],cursor_key='marks',cursor_value=5,chunk_size=2)
    assert cursors==[]


def test_partition_telemetry_is_fail_closed_and_bounded():
    t=ps.partition_telemetry()
    assert t['partitioned'] is True
    assert t['cursor_policy']=='PER_FAMILY_AFTER_ALL_CHUNKS_REMOTE_SUCCESS'
    assert 1 <= t['mark_chunk'] <= ps.MAX_SYNC_BATCH
    assert t['real_trading'] is False


def test_v8_151_cold_path_is_complete_and_nonblocking():
    with v8._DEEP_151_LOCK:
        old=dict(v8._DEEP_151);v8._DEEP_151.update({'matrix':None,'manifest':None,'release':None,'proof':None})
    try:
        out=v8.tasks_151_200_cached()
        assert out['status']=='LITE_READY_FAIL_CLOSED'
        assert out['source_ready'] is True and out['lite_ready'] is True and out['deep_ready'] is False
        assert set(out['tasks'])=={str(i) for i in range(151,201)}
        assert all(x['state']=='NOT_VERIFIED' for x in out['tasks'].values())
        assert out['setup_allowed'] is False and out['real_trading'] is False
    finally:
        with v8._DEEP_151_LOCK:v8._DEEP_151.clear();v8._DEEP_151.update(old)


def test_v8_supabase_health_uses_partitioned_generic_transport(monkeypatch):
    monkeypatch.setattr(v8.partitioned_sync,'sync_telemetry',lambda:{'status':'HEALTHY','configured':True,'partitioned_transport':{'partitioned':True},'real_trading':False})
    monkeypatch.setattr(v8.base7.learning_sync,'learning_sync_telemetry',lambda:{'status':'HEALTHY','configured':True,'real_trading':False})
    monkeypatch.setattr(v8.base7.remote_queue,'probe_telemetry',lambda:{'real_trading':False})
    monkeypatch.setattr(v8.base7._PROVIDER,'telemetry',lambda:{'real_trading':False})
    h=v8.supabase_health_v8()
    assert h['status']=='HEALTHY'
    assert h['generic_sync']['partitioned_transport']['partitioned'] is True
    assert h['real_trading'] is False
