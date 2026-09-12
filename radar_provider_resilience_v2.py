"""Runtime provider resilience primitives for tasks 291-300.

These controls regulate transport only. They cannot authorize releases, promotions,
or real trading.
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

from radar_provider_resilience_v1 import ProviderBulkheads

REAL_TRADING = False


class AdaptiveRateGovernor:
    def __init__(self, min_interval_seconds=0.0, max_interval_seconds=60.0):
        self.min_interval = max(0.0, float(min_interval_seconds))
        self.max_interval = max(self.min_interval, float(max_interval_seconds))
        self._lock = threading.RLock()
        self._next_allowed = defaultdict(float)
        self._interval = defaultdict(lambda: self.min_interval)
        self._rate_limited = defaultdict(int)

    def before(self, provider):
        name = str(provider)
        with self._lock:
            wait = max(0.0, self._next_allowed[name] - time.monotonic())
        if wait > 0:
            time.sleep(min(wait, self.max_interval))

    def success(self, provider):
        name = str(provider)
        with self._lock:
            cur = self._interval[name]
            self._interval[name] = max(self.min_interval, cur * 0.5)
            self._next_allowed[name] = time.monotonic() + self._interval[name]

    def failure(self, provider, kind):
        name = str(provider); k = str(kind or '').lower()
        with self._lock:
            cur = self._interval[name]
            if k in {'429', 'rate_limit'}:
                self._rate_limited[name] += 1
                nxt = max(1.0, cur * 2.0 if cur else 1.0)
            elif k in {'timeout', 'connection', '502', '503', '504', '5xx'}:
                nxt = max(0.5, cur * 1.5 if cur else 0.5)
            else:
                nxt = cur
            self._interval[name] = min(self.max_interval, nxt)
            self._next_allowed[name] = time.monotonic() + self._interval[name]

    def telemetry(self):
        with self._lock:
            return {
                'adaptive_rate_governor': True,
                'interval_seconds': dict(self._interval),
                'rate_limited_events': dict(self._rate_limited),
                'real_trading': False,
            }


class ProviderCircuit:
    def __init__(self, failure_threshold=3, cooldown_seconds=90.0):
        self.threshold = max(2, int(failure_threshold))
        self.cooldown = max(1.0, float(cooldown_seconds))
        self._lock = threading.RLock()
        self._states = defaultdict(lambda: {'failures': 0, 'opened_at': None, 'half_open_probe': False, 'recoveries': 0})

    def state(self, provider):
        name = str(provider)
        with self._lock:
            s = dict(self._states[name])
        if s['opened_at'] is None:
            return 'CLOSED'
        elapsed = time.monotonic() - float(s['opened_at'])
        return 'HALF_OPEN' if elapsed >= self.cooldown else 'OPEN'

    def allow(self, provider):
        name = str(provider)
        with self._lock:
            state = self.state(name)
            s = self._states[name]
            if state == 'CLOSED':
                return True
            if state == 'OPEN':
                return False
            if s['half_open_probe']:
                return False
            s['half_open_probe'] = True
            return True

    def success(self, provider):
        name = str(provider)
        with self._lock:
            s = self._states[name]
            if s['opened_at'] is not None or s['failures']:
                s['recoveries'] += 1
            s.update({'failures': 0, 'opened_at': None, 'half_open_probe': False})

    def failure(self, provider):
        name = str(provider)
        with self._lock:
            s = self._states[name]
            s['failures'] += 1
            s['half_open_probe'] = False
            if s['failures'] >= self.threshold and s['opened_at'] is None:
                s['opened_at'] = time.monotonic()

    def telemetry(self):
        with self._lock:
            names = list(self._states)
            raw = {n: dict(self._states[n]) for n in names}
        return {
            'state_machine': 'CLOSED_OPEN_HALF_OPEN',
            'providers': {n: {**raw[n], 'state': self.state(n)} for n in names},
            'failure_threshold': self.threshold,
            'cooldown_seconds': self.cooldown,
            'real_trading': False,
        }


class ProviderTransportGuard:
    def __init__(self, max_concurrency=4, failure_threshold=3, cooldown_seconds=90.0):
        self.bulkheads = ProviderBulkheads(max_concurrency=max_concurrency)
        self.circuits = ProviderCircuit(failure_threshold=failure_threshold, cooldown_seconds=cooldown_seconds)
        self.rates = AdaptiveRateGovernor()
        self._lock = threading.RLock()
        self._calls = defaultdict(int); self._successes = defaultdict(int); self._failures = defaultdict(int)
        self._latencies = defaultdict(lambda: deque(maxlen=100))

    def call(self, provider, fn, *args, timeout=10, **kwargs):
        name = str(provider)
        if not self.circuits.allow(name):
            raise RuntimeError(f'provider circuit open: {name}')
        self.rates.before(name)
        started = time.monotonic()
        with self._lock:
            self._calls[name] += 1
        try:
            out = self.bulkheads.call(name, fn, *args, timeout=timeout, **kwargs)
            self.circuits.success(name); self.rates.success(name)
            with self._lock:
                self._successes[name] += 1
            return out
        except Exception as exc:
            kind = '429' if '429' in str(exc) else ('timeout' if isinstance(exc, TimeoutError) or 'timed out' in str(exc).lower() else 'error')
            self.circuits.failure(name); self.rates.failure(name, kind)
            with self._lock:
                self._failures[name] += 1
            raise
        finally:
            with self._lock:
                self._latencies[name].append(round((time.monotonic() - started) * 1000.0, 2))

    def telemetry(self):
        with self._lock:
            names = sorted(set(self._calls) | set(self._successes) | set(self._failures))
            calls = dict(self._calls); successes = dict(self._successes); failures = dict(self._failures)
            lat = {n: list(self._latencies[n]) for n in names}
        return {
            'wired': True,
            'bulkhead_isolation': True,
            'providers': {n: {'calls': calls.get(n,0), 'successes': successes.get(n,0), 'failures': failures.get(n,0),
                              'last_latency_ms': lat[n][-1] if lat.get(n) else None} for n in names},
            'circuit': self.circuits.telemetry(),
            'rate_governor': self.rates.telemetry(),
            'reconcile_after_recovery': False,
            'failover_verified': False,
            'real_trading': False,
        }


def resilience_contract():
    return {
        'bulkhead_isolation': True,
        'circuit_states': ['CLOSED', 'OPEN', 'HALF_OPEN'],
        'adaptive_rate_limit': True,
        'provider_failover_requires_two_verified_sources': True,
        'reconciliation_requires_remote_compare': True,
        'network_partition_testable': True,
        'real_trading': False,
    }
