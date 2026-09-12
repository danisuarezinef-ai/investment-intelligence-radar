import io
import json
import urllib.error

import pytest

import radar_learning_sync as sync


class _Response:
    def __init__(self,payload): self.payload=payload
    def __enter__(self): return self
    def __exit__(self,*args): return False
    def read(self): return json.dumps(self.payload).encode('utf-8')


def _http_error(code,body='temporary'):
    return urllib.error.HTTPError('https://example.invalid/learning',code,'error',hdrs=None,fp=io.BytesIO(body.encode()))


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    sync._reset_learning_sync_state_for_tests()
    monkeypatch.setattr(sync,'SYNC_URL','https://example.invalid/learning')
    monkeypatch.setattr(sync,'SYNC_TOKEN','test-token')
    monkeypatch.setattr(sync.random,'uniform',lambda a,b:1.0)
    yield
    sync._reset_learning_sync_state_for_tests()


def test_learning_timeout_retries_then_recovers(monkeypatch):
    calls={'n':0};sleeps=[]
    def fake(req,timeout):
        calls['n']+=1
        if calls['n']==1: raise TimeoutError('temporary')
        return _Response({'ok':True})
    monkeypatch.setattr(sync.urllib.request,'urlopen',fake)
    monkeypatch.setattr(sync.time,'sleep',sleeps.append)
    assert sync._post({'predictions':[{'id':1}]},attempts=3)=={'ok':True}
    assert calls['n']==2 and sleeps==[0.75]
    t=sync.learning_sync_telemetry()
    assert t['status']=='HEALTHY'
    assert t['retry_attempts']==1
    assert t['timeout_means_missing_data'] is False
    assert t['cursors_advance_only_after_remote_success'] is True


def test_learning_nonretryable_http_fails_immediately(monkeypatch):
    calls={'n':0}
    def fake(req,timeout): calls['n']+=1; raise _http_error(400,'bad')
    monkeypatch.setattr(sync.urllib.request,'urlopen',fake)
    monkeypatch.setattr(sync.time,'sleep',lambda _:None)
    with pytest.raises(RuntimeError,match='HTTP 400'): sync._post({'x':1},attempts=3)
    assert calls['n']==1
    assert sync.learning_sync_telemetry()['status']=='DEGRADED'


def test_learning_circuit_opens_after_terminal_failures(monkeypatch):
    calls={'n':0}
    monkeypatch.setattr(sync,'LEARNING_CIRCUIT_FAILURES',2)
    monkeypatch.setattr(sync,'LEARNING_CIRCUIT_COOLDOWN',120.0)
    def fake(req,timeout): calls['n']+=1; raise TimeoutError('down')
    monkeypatch.setattr(sync.urllib.request,'urlopen',fake)
    monkeypatch.setattr(sync.time,'sleep',lambda _:None)
    for _ in range(2):
        with pytest.raises(TimeoutError): sync._post({'x':1},attempts=1)
    assert sync.learning_sync_telemetry()['status']=='CIRCUIT_OPEN'
    with pytest.raises(sync.LearningSyncCircuitOpen): sync._post({'x':2},attempts=1)
    assert calls['n']==2


def test_learning_batch_is_conservatively_bounded():
    assert 50 <= sync.MAX_LEARNING_BATCH <= 500
    assert sync.MAX_LEARNING_BATCH == 250
