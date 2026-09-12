"""Production entrypoint v7: v6 plus pre-1.6 tasks 201-310.

HTTP is always light/fail-closed. Expensive evidence collection is serialized in a
background worker and only enriches snapshots. Windows remains 1.5.28 and
REAL_TRADING=false.
"""
from __future__ import annotations

import os
import threading
import time
from collections import defaultdict, deque

import cloud_service_v6 as base6
import radar_learning_sync as learning_sync
import radar_supabase_sync as generic_sync
from radar_pre160_cache_v7 import AsyncSnapshotCache
from radar_pre160_controls_v7 import build_matrix_201_270
from radar_pre160_controls_v8 import build_matrix_271_310
from radar_pre160_data_authority_v7 import content_hash
from radar_pre160_production_proof_v3 import proof_v3_contract, verify_proof_v3
from radar_pre160_readiness_v4 import DeepWorkScheduler, StageProfiler, TieredReadiness, readiness_contract
from radar_provider_resilience_v2 import ProviderTransportGuard, resilience_contract
import radar_sync_queue_v3 as remote_queue

REAL_TRADING = False
_CACHE = AsyncSnapshotCache(ttl_seconds=60, stale_seconds=600)
_LATENCY = defaultdict(lambda: deque(maxlen=240))
_PROFILER = StageProfiler(max_samples=240)
_SCHEDULER = DeepWorkScheduler(min_interval_seconds=180, max_runtime_seconds=180)
_READINESS = TieredReadiness(cold_budget_ms=1000, hot_budget_ms=250, deep_budget_ms=180000)
_PROVIDER = ProviderTransportGuard(max_concurrency=2, failure_threshold=3, cooldown_seconds=90)
_PREWARM_STARTED = False
_PREWARM_LOCK = threading.Lock()
_QUEUE_PROBE_STARTED = False
_QUEUE_PROBE_LOCK = threading.Lock()
_DEEP_MATRIX = None
_DEEP_MATRIX_LOCK = threading.RLock()


def _quantile(values, q):
    xs = sorted(float(x) for x in values)
    if not xs:
        return None
    if len(xs) == 1:
        return xs[0]
    pos = (len(xs) - 1) * float(q)
    lo = int(pos); hi = min(len(xs) - 1, lo + 1); frac = pos - lo
    return xs[lo] + (xs[hi] - xs[lo]) * frac


def deployment_identity():
    sha = (os.getenv('RAILWAY_GIT_COMMIT_SHA') or os.getenv('RADAR_DEPLOY_REV') or '').strip()
    return {
        'status': 'OBSERVED' if sha else 'NOT_VERIFIED',
        'deployed_sha': sha or None,
        'deployment_id': (os.getenv('RAILWAY_DEPLOYMENT_ID') or '').strip() or None,
        'service_id': (os.getenv('RAILWAY_SERVICE_ID') or '').strip() or None,
        'environment': (os.getenv('RAILWAY_ENVIRONMENT_NAME') or '').strip() or None,
        'source': 'RAILWAY_GIT_COMMIT_SHA' if os.getenv('RAILWAY_GIT_COMMIT_SHA') else ('RADAR_DEPLOY_REV' if os.getenv('RADAR_DEPLOY_REV') else None),
        'setup_allowed': False,
        'can_trade': False,
        'real_trading': False,
    }


def latency_metrics():
    all_values = [v for vals in _LATENCY.values() for v in vals]
    return {
        'p50_ms': round(_quantile(all_values, .50), 2) if all_values else None,
        'p95_ms': round(_quantile(all_values, .95), 2) if all_values else None,
        'p99_ms': round(_quantile(all_values, .99), 2) if all_values else None,
        'hot_p95_ms': round(_quantile(all_values[-60:], .95), 2) if all_values else None,
        'cold_p95_ms': round(_quantile(all_values[:10], .95), 2) if all_values else None,
        'profiled_stages': ['http_v7', 'deep_inputs', 'deep_matrix_201_270', 'deep_total'],
        'stage_budgets_ms': {'http_v7': 1000, 'deep_total': 180000},
        'regression_pct': None,
        'samples': len(all_values),
        'real_trading': False,
    }


def _lite_201_270_matrix():
    tasks = {str(i): {'task': i, 'state': 'NOT_VERIFIED', 'detail': 'deep evidence not ready; light snapshot is fail-closed',
                      'critical': i in {201,202,205,216,220,221,223,230,235,237,238,239,240,249,258,259,260,261,262,269,270}}
             for i in range(201,271)}
    return {
        'status': 'LITE_READY_FAIL_CLOSED',
        'tasks': tasks,
        'groups': {},
        'critical_failed': [],
        'critical_pending': [k for k,v in tasks.items() if v.get('critical')],
        'master_gate': {'status': 'BLOCKED_PRE160', 'manual_review_only': True, 'setup_allowed': False,
                        'automatic_release': False, 'live_execution_allowed': False, 'can_trade': False, 'real_trading': False},
        'source_ready': True,
        'lite_ready': True,
        'deep_ready': False,
        'source_mode': 'TIERED_LITE_FAIL_CLOSED',
        'stable_windows_version': '1.5.28',
        'candidate_version': '1.6.0',
        'setup_allowed': False,
        'setup_built': False,
        'automatic_release': False,
        'automatic_promotion': False,
        'automatic_demotion': False,
        'live_execution_allowed': False,
        'can_trade': False,
        'real_trading': False,
    }


def _build_lite_snapshot():
    value = {
        'status': 'LITE_READY',
        'deployment': deployment_identity(),
        'generic_sync': generic_sync.sync_telemetry(),
        'learning_sync': learning_sync.learning_sync_telemetry(),
        'cache': _CACHE.telemetry(),
        'queue': remote_queue.probe_telemetry(),
        'provider': _PROVIDER.telemetry(),
        'readiness_contract': readiness_contract(),
        'provider_contract': resilience_contract(),
        'proof_v3': verify_proof_v3(),
        'proof_v3_contract': proof_v3_contract(),
        'dependency_token_cache': True,
        'shared_deep_snapshot': True,
        'real_trading': False,
    }
    return _READINESS.set_lite(value)


def _source_inputs():
    """Legacy-compatible expensive hook; only the background deep worker may call it."""
    return base6._inputs()


def _collect_deep():
    global _DEEP_MATRIX
    _READINESS.mark_deep_started()
    started = time.monotonic()
    try:
        evidence, hardening, runtime, health = _PROFILER.timed('deep_inputs', _source_inputs)
        proof = _PROFILER.timed('deep_proof_v1', base6.production_proof_cached)
        prior = _PROFILER.timed('deep_tasks_151_200', base6.tasks_151_200_cached)
        identity = deployment_identity()
        expected = proof.get('audited_commit_sha') if proof.get('verified') is True else None
        matrix = _PROFILER.timed('deep_matrix_201_270', lambda: build_matrix_201_270(
            evidence=evidence, hardening=hardening, runtime=runtime, supabase_health=health, proof=proof,
            cache_telemetry=_CACHE.telemetry(), prior_task_groups=[prior], endpoint_metrics=latency_metrics(),
            deployment={'deployed_sha': identity.get('deployed_sha'), 'expected_sha': expected},
        ))
        matrix = dict(matrix)
        matrix.update({'source_ready': True, 'lite_ready': True, 'deep_ready': True,
                       'source_mode': 'TIERED_DEEP_PREWARMED', 'real_trading': False})
        with _DEEP_MATRIX_LOCK:
            _DEEP_MATRIX = matrix
        token = content_hash({'evidence': evidence.get('snapshot_hash'), 'hardening': hardening.get('snapshot_hash'),
                              'deploy': identity.get('deployed_sha'), 'proof': proof.get('protected_digest')})
        _CACHE.prewarm('201-270', token, lambda m=dict(matrix): m)
        _READINESS.set_deep({'status': 'DEEP_READY', 'matrix_digest': matrix.get('matrix_digest')})
        return matrix
    except Exception as exc:
        _READINESS.set_deep_error(exc)
        raise
    finally:
        _PROFILER.observe('deep_total', (time.monotonic() - started) * 1000.0)


def tasks_201_270_cached(force=False):
    if force:
        _CACHE.invalidate('201-270')
    cached = _CACHE.peek('201-270')
    if isinstance(cached, dict):
        return dict(cached)
    with _DEEP_MATRIX_LOCK:
        if isinstance(_DEEP_MATRIX, dict):
            return dict(_DEEP_MATRIX)
    return _lite_201_270_matrix()


def block(start, end):
    matrix = tasks_201_270_cached(); tasks = matrix.get('tasks') or {}
    return {
        'status': f'PRE160_TASKS_{start}_{end}' if matrix.get('deep_ready') else 'LITE_READY_FAIL_CLOSED',
        'source_ready': True,
        'lite_ready': True,
        'deep_ready': matrix.get('deep_ready') is True,
        'source_mode': matrix.get('source_mode'),
        'tasks': {str(i): tasks.get(str(i)) for i in range(start, end + 1)},
        'setup_allowed': False, 'automatic_release': False, 'automatic_promotion': False,
        'automatic_demotion': False, 'can_trade': False, 'real_trading': False,
    }


def readiness_snapshot():
    lite = _build_lite_snapshot()
    state = _READINESS.state(_PROFILER, _SCHEDULER)
    profile = _PROFILER.telemetry()
    if 'http_v7' not in (profile.get('stages') or {}):
        profile.setdefault('stages', {})['http_v7'] = {'samples': 0, 'p50_ms': None, 'p95_ms': None, 'p99_ms': None, 'max_ms': None}
    state['profiler'] = profile
    state['dependency_token_cache'] = True
    state['shared_deep_snapshot'] = True
    state['lite_snapshot'] = {'status': lite.get('status'), 'deployment': lite.get('deployment')}
    state['real_trading'] = False
    return state


def tasks_271_310_cached():
    r = readiness_snapshot()
    queue = remote_queue.probe_telemetry()
    queue.update(remote_queue.queue_contract())
    proof = verify_proof_v3(); proof['contract'] = proof_v3_contract()
    old = tasks_201_270_cached().get('master_gate') or {}
    deployment = deployment_identity()
    proof_sha = proof.get('audited_commit_sha') if proof.get('verified') else None
    return build_matrix_271_310(
        readiness=r,
        queue=queue,
        provider=_PROVIDER.telemetry(),
        generic_sync=generic_sync.sync_telemetry(),
        learning_sync=learning_sync.learning_sync_telemetry(),
        proof_v3=proof,
        deployment={'expected_sha': proof_sha, 'deployed_sha': deployment.get('deployed_sha')},
        ci_evidence={},
        prior_gate=old,
    )


def _prewarm_loop():
    while True:
        try:
            _build_lite_snapshot()
            _SCHEDULER.run(_collect_deep)
        except Exception as exc:
            print('[pre160-v7-deep] '+repr(exc), flush=True)
        time.sleep(30)


def _ensure_prewarm():
    global _PREWARM_STARTED
    with _PREWARM_LOCK:
        if _PREWARM_STARTED:
            return
        _PREWARM_STARTED = True
        _build_lite_snapshot()
        threading.Thread(target=_prewarm_loop, name='pre160-v7-deep-prewarm', daemon=True).start()


def _queue_probe_loop():
    time.sleep(2)
    while True:
        try:
            _PROVIDER.call('supabase-retry-queue', remote_queue.durability_probe, timeout=10)
            _PROVIDER.call('supabase-retry-queue', remote_queue.remote_stats, timeout=10)
        except Exception as exc:
            print('[pre160-queue-v3] '+repr(exc), flush=True)
        time.sleep(900)


def _ensure_queue_probe():
    global _QUEUE_PROBE_STARTED
    with _QUEUE_PROBE_LOCK:
        if _QUEUE_PROBE_STARTED:
            return
        _QUEUE_PROBE_STARTED = True
        threading.Thread(target=_queue_probe_loop, name='pre160-queue-durability', daemon=True).start()


class ValidationV7Handler(base6.ValidationV6Handler):
    def do_GET(self):
        path = self.path.split('?', 1)[0]; started = time.monotonic()
        try:
            if path == '/pre160-audit-201-270-v1': self._send(200, tasks_201_270_cached()); return
            if path == '/pre160-resilience-v7': self._send(200, block(201,220)); return
            if path == '/pre160-data-authority-v7': self._send(200, block(221,240)); return
            if path == '/pre160-statistical-validity-v7': self._send(200, block(241,260)); return
            if path == '/pre160-autonomy-v7': self._send(200, block(261,270)); return
            if path == '/pre160-readiness-v4': self._send(200, readiness_snapshot()); return
            if path == '/pre160-queue-v3': self._send(200, {**remote_queue.probe_telemetry(), **remote_queue.queue_contract()}); return
            if path == '/pre160-provider-resilience-v2': self._send(200, _PROVIDER.telemetry()); return
            if path == '/pre160-proof-v3': self._send(200, {**verify_proof_v3(), 'contract': proof_v3_contract()}); return
            if path == '/pre160-audit-271-310-v1': self._send(200, tasks_271_310_cached()); return
            if path == '/pre160-master-gate-v4': self._send(200, tasks_271_310_cached().get('master_gate_v4') or {}); return
            if path == '/pre160-master-gate-v3':
                matrix = tasks_201_270_cached(); x = dict(matrix.get('master_gate') or {})
                x.update({'source_ready': True, 'lite_ready': True, 'deep_ready': matrix.get('deep_ready') is True, 'real_trading': False})
                self._send(200, x); return
            if path == '/pre160-cache-v7': self._send(200, {**_CACHE.telemetry(), 'tiered_readiness': readiness_snapshot()}); return
            if path == '/pre160-deployment-v7': self._send(200, deployment_identity()); return
        except Exception as exc:
            self._send(500, {'status':'FAILED','error':str(exc)[:800],'source_ready':False,'setup_allowed':False,
                             'automatic_release':False,'automatic_promotion':False,'automatic_demotion':False,
                             'can_trade':False,'real_trading':False}); return
        finally:
            if path.startswith('/pre160-'):
                elapsed = round((time.monotonic() - started) * 1000.0, 2)
                _LATENCY[path].append(elapsed)
                _PROFILER.observe('http_v7', elapsed)
        super().do_GET()


def start_runtime():
    runtime = base6.start_runtime()
    runtime.run_worker._Handler = ValidationV7Handler
    _ensure_prewarm(); _ensure_queue_probe()
    return runtime


if __name__ == '__main__':
    runtime = start_runtime(); runtime.run_worker.main()
