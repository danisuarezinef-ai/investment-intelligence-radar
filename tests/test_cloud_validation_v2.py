import cloud_service_v2 as csv2


def _handler(path):
    h = object.__new__(csv2.ValidationHandler)
    h.path = path
    sent = {}
    h._send = lambda code, payload: sent.update(code=code, payload=payload)
    return h, sent


def test_validation_endpoint_is_read_only(monkeypatch):
    monkeypatch.setattr(csv2, 'validation_runtime_snapshot', lambda: {
        'ready_for_live_review': True,
        'can_trade': True,
        'auto_promote': True,
        'real_trading': True,
    })
    h, sent = _handler('/validation-v2')
    h.do_GET()
    assert sent['code'] == 200
    assert sent['payload']['ready_for_live_review'] is True
    assert sent['payload']['can_trade'] is False
    assert sent['payload']['auto_promote'] is False
    assert sent['payload']['real_trading'] is False


def test_validation_endpoint_errors_fail_closed(monkeypatch):
    def boom():
        raise RuntimeError('validation unavailable')
    monkeypatch.setattr(csv2, 'validation_runtime_snapshot', boom)
    h, sent = _handler('/validation-v2')
    h.do_GET()
    assert sent['code'] == 500
    assert sent['payload']['can_trade'] is False
    assert sent['payload']['auto_promote'] is False
    assert sent['payload']['real_trading'] is False
