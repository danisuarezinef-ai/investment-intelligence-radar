import json
import cloud_service_v3 as svc


def test_structured_heartbeat_detail_is_serialized(monkeypatch):
    captured={}
    def fake(*args,**kwargs):
        captured.update(kwargs)
        return {'node_id':'pc'}
    monkeypatch.setattr(svc,'_original_sync_node_heartbeat',fake)
    out=svc._safe_sync_node_heartbeat('pc',detail={'bridge':'railway','ok':True})
    assert out['node_id']=='pc'
    assert isinstance(captured['detail'],str)
    assert json.loads(captured['detail'])=={'bridge':'railway','ok':True}


def test_string_heartbeat_detail_is_unchanged(monkeypatch):
    captured={}
    def fake(*args,**kwargs):
        captured.update(kwargs)
        return {'node_id':'pc'}
    monkeypatch.setattr(svc,'_original_sync_node_heartbeat',fake)
    svc._safe_sync_node_heartbeat('pc',detail='ready')
    assert captured['detail']=='ready'
    assert svc.REAL_TRADING is False
