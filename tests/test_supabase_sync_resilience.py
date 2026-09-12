import io
import inspect
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


@pytest.fixture(autouse=True)
def _reset_resilience(monkeypatch):
    sync._reset_resilience_state_for_tests()
    monkeypatch.setattr(sync, 'SYNC_URL', 'https://example.invalid/sync')
    monkeypatch.setattr(sync, 'SYNC_TOKEN', 'test-token')
    monkeypatch.setattr(sync.random, 'uniform', lambda a, b: 1.0)
    yield
    sync._reset_resilience_state_for_tests()


def test_retryable_http_error_retries_then_succeeds(monkeypatch):
    calls = {'n': 0}
    sleeps = []

    def fake_urlopen(req, timeout):
        calls['n'] += 1
        if calls['n'] == 1:
            raise _http_error(500)
        return _Response({'ok': True})

    monkeypatch.setattr(sync.urllib.request, 'urlopen', fake_urlopen)
    monkeypatch.setattr(sync.time, 'sleep', sleeps.append)

    assert sync._post({'x': 1}, attempts=3) == {'ok': True}
    assert calls['n'] == 2
    assert sleeps == [0.75]
    telemetry = sync.sync_telemetry()
    assert telemetry['status'] == 'HEALTHY'
    assert telemetry['retry_attempts'] == 1
    assert telemetry['successes'] == 1


def test_non_retryable_http_error_fails_immediately(monkeypatch):
    calls = {'n': 0}

    def fake_urlopen(req, timeout):
        calls['n'] += 1
        raise _http_error(400, 'bad request')

    monkeypatch.setattr(sync.urllib.request, 'urlopen', fake_urlopen)
    monkeypatch.setattr(sync.time, 'sleep', lambda _: None)

    with pytest.raises(RuntimeError, match='HTTP 400'):
        sync._post({'x': 1}, attempts=3)
    assert calls['n'] == 1
    telemetry = sync.sync_telemetry()
    assert telemetry['status'] == 'DEGRADED'
    assert telemetry['terminal_failures'] == 1
    assert telemetry['last_error_type'] == 'RuntimeError'


def test_timeout_retries_but_eventually_fails_without_fabricating_zero(monkeypatch):
    calls = {'n': 0}

    def fake_urlopen(req, timeout):
        calls['n'] += 1
        raise TimeoutError('timed out')

    monkeypatch.setattr(sync.urllib.request, 'urlopen', fake_urlopen)
    monkeypatch.setattr(sync.time, 'sleep', lambda _: None)

    with pytest.raises(TimeoutError):
        sync._post({'market_snapshots': [{'id': 1}]}, attempts=3)
    assert calls['n'] == 3
    telemetry = sync.sync_telemetry()
    assert telemetry['retry_attempts'] == 2
    assert telemetry['last_error_type'] == 'TimeoutError'
    assert telemetry['timeout_means_missing_data'] is False
    assert telemetry['empty_response_means_zero_evidence'] is False
    assert telemetry['last_batch_counts']['market_snapshots'] == 1


def test_circuit_breaker_opens_after_bounded_terminal_failures(monkeypatch):
    calls = {'n': 0}
    monkeypatch.setattr(sync, 'CIRCUIT_FAILURE_THRESHOLD', 2)
    monkeypatch.setattr(sync, 'CIRCUIT_COOLDOWN_SECONDS', 120.0)

    def fake_urlopen(req, timeout):
        calls['n'] += 1
        raise TimeoutError('down')

    monkeypatch.setattr(sync.urllib.request, 'urlopen', fake_urlopen)
    monkeypatch.setattr(sync.time, 'sleep', lambda _: None)

    for _ in range(2):
        with pytest.raises(TimeoutError):
            sync._post({'x': 1}, attempts=1)
    assert calls['n'] == 2
    assert sync.sync_telemetry()['status'] == 'CIRCUIT_OPEN'
    with pytest.raises(sync.SupabaseCircuitOpen):
        sync._post({'x': 2}, attempts=1)
    assert calls['n'] == 2  # fail-fast: no extra network request while open


def test_success_after_failure_records_recovery(monkeypatch):
    calls = {'n': 0}

    def fake_urlopen(req, timeout):
        calls['n'] += 1
        if calls['n'] == 1:
            raise TimeoutError('temporary')
        return _Response({'ok': True})

    monkeypatch.setattr(sync.urllib.request, 'urlopen', fake_urlopen)
    monkeypatch.setattr(sync.time, 'sleep', lambda _: None)

    with pytest.raises(TimeoutError):
        sync._post({'x': 1}, attempts=1)
    assert sync._post({'x': 1}, attempts=1) == {'ok': True}
    telemetry = sync.sync_telemetry()
    assert telemetry['recoveries'] == 1
    assert telemetry['consecutive_failures'] == 0
    assert telemetry['status'] == 'HEALTHY'


def test_sync_cursors_advance_only_after_remote_post_success():
    source = inspect.getsource(sync.sync_once)
    post_at = source.index('result = _post(payload)')
    for key in (
        'supabase_market_id', 'supabase_event_id', 'supabase_run_id',
        'supabase_agent_trade_id', 'supabase_agent_mark_id',
        'supabase_alert_id', 'supabase_notification_id',
    ):
        assert source.index(f"_control_set('{key}'", post_at) > post_at
    assert sync.sync_telemetry()['cursors_advance_only_after_remote_success'] is True


def test_sync_batch_is_conservatively_capped():
    assert sync.MAX_SYNC_BATCH == 250


def test_origin_id_is_bigint_safe_and_preserves_local_order(monkeypatch):
    monkeypatch.setattr(sync, '_SYNC_PREFIX', 123456)
    first = sync._origin_id(1)
    second = sync._origin_id(2)
    assert isinstance(first, str) and isinstance(second, str)
    assert int(first) != 1
    assert int(second) == int(first) + 1
    assert 0 <= int(first) < 2**63
    assert json.loads(json.dumps({'origin_id': first}))['origin_id'] == first


def test_ephemeral_sessions_cannot_reuse_same_remote_origin_key(monkeypatch):
    monkeypatch.setattr(sync, '_SYNC_PREFIX', 111)
    old_deploy = sync._origin_id(1)
    monkeypatch.setattr(sync, '_SYNC_PREFIX', 222)
    new_deploy = sync._origin_id(1)
    assert old_deploy != new_deploy


def test_origin_id_rejects_values_outside_uint32(monkeypatch):
    monkeypatch.setattr(sync, '_SYNC_PREFIX', 1)
    with pytest.raises(ValueError):
        sync._origin_id(2**32)
