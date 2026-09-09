import cloud_service_v3 as cloud


def test_validation_v3_endpoint_is_read_only(monkeypatch):
    monkeypatch.setattr(cloud,'validation_runtime_v3',lambda:{'runtime_version':'v3','can_trade':True,'auto_promote':True,'real_trading':True})
    h=cloud.ValidationV3Handler.__new__(cloud.ValidationV3Handler)
    h.path='/validation-v3'
    sent=[]
    h._send=lambda code,payload: sent.append((code,payload))
    h.do_GET()
    assert sent[0][0]==200
    payload=sent[0][1]
    assert payload['runtime_version']=='v3'
    assert payload['can_trade'] is False
    assert payload['auto_promote'] is False
    assert payload['real_trading'] is False
