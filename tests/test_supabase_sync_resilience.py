import io
import json
import urllib.error

import pytest

import radar_supabase_sync as sync


class _Response:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return json.dumps(self.payload).encode('utf-8')


def _http_error(code, body='temporary failure'):
    return urllib.error.HTTPError(
        'https://example.invalid/sync',
        code,
        'error',
        hdrs=None,
        fp=io.BytesIO(body.encode('utf-8')),
    )


def test_retryable_http_error_retries_then_succeeds(monkeypatch):
    sync.SYNC_URL = 'https://example.invalid/sync'
    calls = {'n': 0}

    def fake_urlopen(req, timeout):
        calls['n'] += 1
        if calls['n'] == 1:
            raise _http_error(500)
        return _Response({'ok': True})

    monkeypatch.setattr(sync.urllib.request, 'urlopen', fake_urlopen)
    monkeypatch.setattr(sync.time, 'sleep', lambda _: None)

    assert sync._post({'x': 1}, attempts=3) == {'ok': True}
    assert calls['n'] == 2


def test_non_retryable_http_error_fails_immediately(monkeypatch):
    sync.SYNC_URL = 'https://example.invalid/sync'
    calls = {'n': 0}

    def fake_urlopen(req, timeout):
        calls['n'] += 1
        raise _http_error(400, 'bad request')

    monkeypatch.setattr(sync.urllib.request, 'urlopen', fake_urlopen)
    monkeypatch.setattr(sync.time, 'sleep', lambda _: None)

    with pytest.raises(RuntimeError, match='HTTP 400'):
        sync._post({'x': 1}, attempts=3)
    assert calls['n'] == 1


def test_timeout_retries_but_eventually_fails(monkeypatch):
    sync.SYNC_URL = 'https://example.invalid/sync'
    calls = {'n': 0}

    def fake_urlopen(req, timeout):
        calls['n'] += 1
        raise TimeoutError('timed out')

    monkeypatch.setattr(sync.urllib.request, 'urlopen', fake_urlopen)
    monkeypatch.setattr(sync.time, 'sleep', lambda _: None)

    with pytest.raises(TimeoutError):
        sync._post({'x': 1}, attempts=3)
    assert calls['n'] == 3


def test_sync_batch_is_conservatively_capped():
    assert sync.MAX_SYNC_BATCH == 250
