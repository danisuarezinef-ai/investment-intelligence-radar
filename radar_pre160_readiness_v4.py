"""Tiered pre-1.6 readiness, profiling and resource-budget controller (tasks 271-280).

The light snapshot is safe to serve immediately. Deep evidence collection runs in a
single background slot and can only enrich readiness; it cannot authorize release or
real trading.
"""
from __future__ import annotations

import math
import threading
import time
from collections import defaultdict, deque

REAL_TRADING = False
VALID_STATES = {'WARMING', 'LITE_READY', 'DEEP_READY', 'DEGRADED', 'FAILED'}


class DeepWorkScheduler:
    def __init__(self, min_interval_seconds=30.0, max_runtime_seconds=180.0):
        self.min_interval_seconds = max(5.0, float(min_interval_seconds))
        self.max_runtime_seconds = max(15.0, float(max_runtime_seconds))
        self._lock = threading.RLock()
        self._running = False
        self._last_started = None
        self._last_finished = None
        self._last_runtime_ms = None
        self._runs = 0
        self._skipped_overlap = 0
        self._last_error = None

    def can_start(self):
        with self._lock:
            if self._running:
                return False
            if self._last_started is None:
                return True
            return time.monotonic() - self._last_started >= self.min_interval_seconds

    def run(self, fn):
        with self._lock:
            if not self.can_start():
                self._skipped_overlap += 1
                return {'started': False, 'reason': 'BUSY_OR_INTERVAL'}
            self._running = True
            self._last_started = time.monotonic()
            self._runs += 1
        started = time.monotonic()
        try:
            value = fn()
            elapsed_ms = (time.monotonic() - started) * 1000.0
            with self._lock:
                self._last_runtime_ms = elapsed_ms
                self._last_finished = time.monotonic()
                self._last_error = None
            return {'started': True, 'value': value, 'elapsed_ms': elapsed_ms}
        except Exception as exc:
            elapsed_ms = (time.monotonic() - started) * 1000.0
            with self._lock:
                self._last_runtime_ms = elapsed_ms
                self._last_finished = time.monotonic()
                self._last_error = f'{type(exc).__name__}: {str(exc)[:500]}'
            raise
        finally:
            with self._lock:
                self._running = False

    def telemetry(self):
        with self._lock:
            t = {
                'running': self._running,
                'runs': self._runs,
                'skipped_overlap': self._skipped_overlap,
                'last_runtime_ms': self._last_runtime_ms,
                'last_error': self._last_error,
                'serialized_deep_work': True,
                'min_interval_seconds': self.min_interval_seconds,
                'max_runtime_seconds': self.max_runtime_seconds,
                'cpu_io_budget_policy': 'ONE_DEEP_JOB_AT_A_TIME',
                'real_trading': False,
            }
        return t


class StageProfiler:
    def __init__(self, max_samples=120):
        self._lock = threading.RLock()
        self._samples = defaultdict(lambda: deque(maxlen=max_samples))
        self._last_error = None

    def observe(self, stage, elapsed_ms):
        with self._lock:
            self._samples[str(stage)].append(float(elapsed_ms))

    def timed(self, stage, fn):
        started = time.monotonic()
        try:
            return fn()
        except Exception as exc:
            with self._lock:
                self._last_error = f'{stage}:{type(exc).__name__}:{str(exc)[:300]}'
            raise
        finally:
            self.observe(stage, (time.monotonic() - started) * 1000.0)

    @staticmethod
    def _quantile(values, q):
        xs = sorted(float(x) for x in values)
        if not xs:
            return None
        if len(xs) == 1:
            return xs[0]
        pos = (len(xs) - 1) * float(q)
        lo = int(math.floor(pos)); hi = int(math.ceil(pos))
        if lo == hi:
            return xs[lo]
        return xs[lo] + (xs[hi] - xs[lo]) * (pos - lo)

    def telemetry(self):
        with self._lock:
            out = {}
            for stage, vals in self._samples.items():
                xs = list(vals)
                out[stage] = {
                    'samples': len(xs),
                    'p50_ms': round(self._quantile(xs, .50), 2) if xs else None,
                    'p95_ms': round(self._quantile(xs, .95), 2) if xs else None,
                    'p99_ms': round(self._quantile(xs, .99), 2) if xs else None,
                    'max_ms': round(max(xs), 2) if xs else None,
                }
            return {'stages': out, 'last_error': self._last_error, 'real_trading': False}


class TieredReadiness:
    def __init__(self, cold_budget_ms=1000.0, hot_budget_ms=250.0, deep_budget_ms=180000.0):
        self.cold_budget_ms = float(cold_budget_ms)
        self.hot_budget_ms = float(hot_budget_ms)
        self.deep_budget_ms = float(deep_budget_ms)
        self._lock = threading.RLock()
        self._lite = None
        self._deep = None
        self._deep_error = None
        self._deep_started_epoch = None
        self._deep_finished_epoch = None

    def set_lite(self, payload):
        value = dict(payload or {})
        value.update({'source_ready': True, 'lite_ready': True, 'real_trading': False})
        with self._lock:
            self._lite = value
        return value

    def mark_deep_started(self):
        with self._lock:
            self._deep_started_epoch = time.time()
            self._deep_error = None

    def set_deep(self, payload):
        value = dict(payload or {})
        value.update({'source_ready': True, 'lite_ready': True, 'deep_ready': True, 'real_trading': False})
        with self._lock:
            self._deep = value
            self._deep_finished_epoch = time.time()
            self._deep_error = None
        return value

    def set_deep_error(self, exc):
        with self._lock:
            self._deep_error = f'{type(exc).__name__}: {str(exc)[:500]}'
            self._deep_finished_epoch = time.time()

    def state(self, profiler=None, scheduler=None):
        with self._lock:
            lite = dict(self._lite) if isinstance(self._lite, dict) else None
            deep = dict(self._deep) if isinstance(self._deep, dict) else None
            err = self._deep_error
            started = self._deep_started_epoch
            finished = self._deep_finished_epoch
        profile = profiler.telemetry() if profiler is not None else {'stages': {}}
        deep_p95 = ((profile.get('stages') or {}).get('deep_total') or {}).get('p95_ms')
        if lite is None:
            status = 'WARMING'
        elif err:
            status = 'DEGRADED'
        elif deep is None:
            status = 'LITE_READY'
        elif deep_p95 is not None and float(deep_p95) > self.deep_budget_ms:
            status = 'DEGRADED'
        else:
            status = 'DEEP_READY'
        if status not in VALID_STATES:
            status = 'FAILED'
        return {
            'status': status,
            'source_ready': lite is not None,
            'lite_ready': lite is not None,
            'deep_ready': deep is not None,
            'deep_error': err,
            'deep_started_epoch': started,
            'deep_finished_epoch': finished,
            'budgets_ms': {'cold_http': self.cold_budget_ms, 'hot_http': self.hot_budget_ms, 'deep_total': self.deep_budget_ms},
            'profiler': profile,
            'scheduler': scheduler.telemetry() if scheduler is not None else None,
            'fail_closed_when_not_deep': True,
            'automatic_release': False,
            'can_trade': False,
            'real_trading': False,
        }

    def best_snapshot(self):
        with self._lock:
            if isinstance(self._deep, dict):
                return dict(self._deep)
            if isinstance(self._lite, dict):
                return dict(self._lite)
        return None


def readiness_contract():
    return {
        'tiered_snapshot': True,
        'state_machine': sorted(VALID_STATES),
        'single_deep_worker': True,
        'dependency_token_cache': True,
        'stale_while_revalidate': True,
        'cold_http_budget_ms': 1000,
        'hot_http_budget_ms': 250,
        'deep_budget_ms': 180000,
        'real_trading': False,
    }
