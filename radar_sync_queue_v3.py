"""Supabase-backed durable retry/dead-letter queue for pre-1.6.

This transport layer has no trading or release authority. Queue ids are content-addressed,
ACKs are issued only after the caller confirms remote success, and durability is verified
across Railway deployment identities via harmless probe rows. Controlled DLQ probes contain
no market, portfolio, order or investment data.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
import time
import urllib.error
import urllib.request

from radar_supabase_sync import SYNC_TOKEN, SYNC_URL

REAL_TRADING = False
MAX_ATTEMPTS = 6
HTTP_TIMEOUT_SECONDS = max(3.0, float(os.environ.get('RADAR_RETRY_QUEUE_TIMEOUT_SECONDS', '8') or 8))
_LOCK = threading.RLock()
_STATE = {
    'requests': 0,
    'successes': 0,
    'failures': 0,
    'last_error': None,
    'last_latency_ms': None,
    'last_success_epoch': None,
    'last_stats': None,
    'cross_redeploy_verified': False,
    'previous_deployment': None,
    'current_deployment': None,
    'probe_epoch': None,
    'controlled_dlq_verified': False,
    'controlled_reprocess_verified': False,
    'controlled_probe_error': None,
    'controlled_probe_epoch': None,
}


def _queue_url():
    explicit = os.environ.get('SUPABASE_RETRY_QUEUE_URL', '').strip()
    if explicit:
        return explicit
    url = (SYNC_URL or '').strip()
    if '/radar-sync' in url:
        return url.rsplit('/radar-sync', 1)[0] + '/radar-retry-queue'
    return ''


def enabled():
    return bool(_queue_url() and SYNC_TOKEN)


def _deployment_id():
    return (
        os.environ.get('RAILWAY_DEPLOYMENT_ID', '').strip()
        or os.environ.get('RADAR_DEPLOYMENT_ID', '').strip()
        or os.environ.get('RAILWAY_GIT_COMMIT_SHA', '').strip()
        or 'unknown-deployment'
    )


def _node_id():
    return os.environ.get('RADAR_NODE_ID', 'cloud-primary').strip() or 'cloud-primary'


def _canonical(payload):
    return json.dumps(payload, sort_keys=True, separators=(',', ':'), ensure_ascii=False, default=str)


def payload_hash(payload):
    return hashlib.sha256(_canonical(payload).encode('utf-8')).hexdigest()


def queue_id(channel, payload):
    raw = _canonical({'channel': str(channel), 'payload': payload})
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


def _post(action, **body):
    if not enabled():
        raise RuntimeError('remote retry queue not configured')
    payload = {'action': str(action), **body}
    raw = json.dumps(payload, ensure_ascii=False, default=str).encode('utf-8')
    req = urllib.request.Request(
        _queue_url(), data=raw, method='POST',
        headers={'Content-Type': 'application/json', 'X-Radar-Token': SYNC_TOKEN,
                 'User-Agent': 'InvestmentIntelligenceRadarQueue/3'},
    )
    started = time.monotonic()
    with _LOCK:
        _STATE['requests'] += 1
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_SECONDS) as r:
            out = json.loads(r.read().decode('utf-8'))
        if out.get('ok') is not True:
            raise RuntimeError('remote queue rejected request')
        with _LOCK:
            _STATE['successes'] += 1
            _STATE['last_error'] = None
            _STATE['last_latency_ms'] = round((time.monotonic() - started) * 1000.0, 2)
            _STATE['last_success_epoch'] = time.time()
        return out
    except (urllib.error.URLError, TimeoutError, OSError, ValueError, RuntimeError) as exc:
        with _LOCK:
            _STATE['failures'] += 1
            _STATE['last_error'] = f'{type(exc).__name__}: {str(exc)[:500]}'
            _STATE['last_latency_ms'] = round((time.monotonic() - started) * 1000.0, 2)
        raise


def enqueue(channel, payload, *, origin_deployment=None):
    item = {
        'id': queue_id(channel, payload),
        'channel': str(channel),
        'payload': payload,
        'payload_hash': payload_hash(payload),
        'origin_node': _node_id(),
        'origin_deployment': origin_deployment or _deployment_id(),
    }
    out = _post('enqueue', items=[item], max_attempts=MAX_ATTEMPTS)
    return {'id': item['id'], 'remote': out, 'real_trading': False}


def due(limit=100):
    out = _post('due', limit=max(1, min(200, int(limit))))
    return list(out.get('items') or [])


def acknowledge(ids):
    ids = [str(x) for x in ids if x]
    if not ids:
        return {'ok': True, 'acked': 0, 'real_trading': False}
    out = _post('ack', ids=ids[:200])
    out['real_trading'] = False
    return out


def fail(items, *, max_attempts=MAX_ATTEMPTS):
    out = _post('fail', items=list(items or [])[:100], max_attempts=max(1, min(20, int(max_attempts))))
    out['real_trading'] = False
    return out


def dead_letters(channel=None, limit=100):
    out = _post('dead', channel=str(channel or ''), limit=max(1, min(200, int(limit))))
    return list(out.get('items') or [])


def requeue_dead_letter(ids):
    ids = [str(x) for x in ids if x]
    if not ids:
        return {'ok': True, 'requeued': 0, 'real_trading': False}
    out = _post('requeue', ids=ids[:100])
    out['real_trading'] = False
    return out


def remote_stats():
    out = _post('stats')
    with _LOCK:
        _STATE['last_stats'] = dict(out)
    return {**out, 'real_trading': False}


def durability_probe():
    """Verify that a probe written by a prior Railway deployment is still present."""
    current = _deployment_id()
    channel = 'pre160_durability_probe'
    probe = _post('probe', channel=channel)
    prior = [x for x in (probe.get('items') or []) if str(x.get('origin_deployment') or '') not in ('', current)]
    cross = bool(prior)
    if prior:
        acknowledge([x.get('id') for x in prior if x.get('id')])
    marker = {'kind': 'durability_probe', 'deployment': current, 'written_at_epoch': round(time.time(), 3), 'trading': False}
    enqueue(channel, marker, origin_deployment=current)
    with _LOCK:
        _STATE['cross_redeploy_verified'] = cross
        _STATE['previous_deployment'] = prior[0].get('origin_deployment') if prior else None
        _STATE['current_deployment'] = current
        _STATE['probe_epoch'] = time.time()
    return probe_telemetry()


def controlled_dlq_probe():
    """Exercise remote retry→DLQ→requeue→ACK with a harmless non-investment payload.

    This probe is intentionally isolated on its own channel. It never contains symbols,
    prices, allocations, orders or portfolio state and cannot authorize any action.
    """
    if not enabled():
        return {'status': 'NOT_CONFIGURED', 'real_trading': False}
    channel = 'pre160_controlled_dlq_probe'
    current = _deployment_id()
    payload = {
        'kind': 'invalid_probe',
        'deployment': current,
        'nonce_epoch': round(time.time(), 6),
        'investment_data': False,
        'trading': False,
    }
    qid = None
    try:
        qid = enqueue(channel, payload, origin_deployment=current)['id']
        final = None
        for _ in range(MAX_ATTEMPTS):
            final = fail([{'id': qid, 'error': 'controlled_invalid_probe', 'retry_after_seconds': 1}], max_attempts=MAX_ATTEMPTS)
        dead = dead_letters(channel, 20)
        in_dead = any(str(x.get('id')) == qid for x in dead)
        if not in_dead or int((final or {}).get('dead') or 0) < 1:
            raise RuntimeError('controlled probe did not reach remote dead letter')
        requeued = requeue_dead_letter([qid])
        if int(requeued.get('requeued') or 0) != 1:
            raise RuntimeError('controlled dead-letter probe was not requeued')
        remaining_dead = dead_letters(channel, 20)
        if any(str(x.get('id')) == qid for x in remaining_dead):
            raise RuntimeError('controlled probe remained in dead letter after requeue')
        acknowledge([qid])
        with _LOCK:
            _STATE['controlled_dlq_verified'] = True
            _STATE['controlled_reprocess_verified'] = True
            _STATE['controlled_probe_error'] = None
            _STATE['controlled_probe_epoch'] = time.time()
        return {'status': 'PASS', 'id': qid, 'dead_letter_verified': True,
                'reprocess_verified': True, 'cleaned_up': True, 'real_trading': False}
    except Exception as exc:
        # Best-effort cleanup must never hide the failure.
        if qid:
            try:
                requeue_dead_letter([qid])
            except Exception:
                pass
            try:
                acknowledge([qid])
            except Exception:
                pass
        with _LOCK:
            _STATE['controlled_probe_error'] = f'{type(exc).__name__}: {str(exc)[:500]}'
            _STATE['controlled_probe_epoch'] = time.time()
        raise


def probe_telemetry():
    with _LOCK:
        s = dict(_STATE)
        if isinstance(s.get('last_stats'), dict):
            s['last_stats'] = dict(s['last_stats'])
    s.update({
        'configured': enabled(),
        'durable_backend': 'SUPABASE' if enabled() else None,
        'dead_letter_remote': True if enabled() else False,
        'ack_after_remote_success': True,
        'content_addressed_ids': True,
        'max_attempts': MAX_ATTEMPTS,
        'controlled_probe_is_non_investment': True,
        'real_trading': False,
    })
    return s


def queue_contract():
    t = probe_telemetry()
    return {
        'durable': enabled(),
        'remote_backend': t.get('durable_backend'),
        'remote_stats_verified': isinstance(t.get('last_stats'), dict) and t['last_stats'].get('ok') is True,
        'cross_redeploy_verified': t.get('cross_redeploy_verified') is True,
        'dead_letter': t.get('dead_letter_remote') is True,
        'controlled_dlq_verified': t.get('controlled_dlq_verified') is True,
        'controlled_reprocess_verified': t.get('controlled_reprocess_verified') is True,
        'max_attempts': MAX_ATTEMPTS,
        'ack_after_remote_success': True,
        'idempotency_key': 'sha256(channel+canonical_payload)',
        'real_trading': False,
    }
