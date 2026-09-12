"""Pre-1.6 resilience controls for tasks 201-220.

Read-only/fail-closed.  Nothing in this module can place orders, publish a Windows
release, promote a model, or turn missing evidence into a pass.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

REAL_TRADING = False
STATES = frozenset({'PASS', 'PENDING_SAMPLE', 'PENDING_TIME', 'NOT_VERIFIED', 'FAILED'})
COLD_ENDPOINT_BUDGET_MS = 25_000.0
HOT_ENDPOINT_BUDGET_MS = 1_000.0
ROUNDTRIP_BUDGET_MS = 30_000.0


def _task(task_id: int, state: str, detail: str, *, critical: bool = False, evidence: Any = None):
    if state not in STATES:
        raise ValueError(state)
    out = {'task': task_id, 'state': state, 'detail': detail, 'critical': bool(critical)}
    if evidence is not None:
        out['evidence'] = evidence
    return out


def classify_retry(error_kind: str) -> dict:
    """Task 217: deterministic retry taxonomy; validation failures never retry."""
    kind = str(error_kind or '').lower()
    if kind in {'timeout', 'connection', '429', 'rate_limit', '502', '503', '504', '5xx'}:
        return {'retry': True, 'bounded': True, 'backoff': 'EXPONENTIAL_JITTER', 'real_trading': False}
    if kind in {'409', 'conflict'}:
        return {'retry': True, 'bounded': True, 'backoff': 'RECONCILE_THEN_RETRY', 'real_trading': False}
    return {'retry': False, 'bounded': True, 'backoff': 'NONE', 'real_trading': False}


def queue_contract(config: dict | None) -> dict:
    c = config or {}
    durable = c.get('durable') is True
    bounded = isinstance(c.get('max_attempts'), int) and 1 <= c['max_attempts'] <= 20
    dlq = c.get('dead_letter') is True
    ack = c.get('ack_after_remote_success') is True
    return {'durable': durable, 'bounded': bounded, 'dead_letter': dlq, 'ack_after_remote_success': ack,
            'pass': durable and bounded and dlq and ack, 'real_trading': False}


def _latency_state(value: Any, budget: float, label: str):
    try:
        ms = float(value)
    except (TypeError, ValueError):
        return 'NOT_VERIFIED', f'no {label} latency evidence'
    return ('PASS', f'{label} {ms:.2f} ms <= {budget:.0f} ms') if ms <= budget else ('FAILED', f'{label} {ms:.2f} ms > {budget:.0f} ms')


def build_resilience_tasks(*, proof: dict, deployment: dict, endpoint_metrics: dict, cache: dict,
                           supabase_health: dict, provider_controls: dict | None = None,
                           queue: dict | None = None, roundtrip_ms: Any = None) -> dict:
    proof = proof or {}; deployment = deployment or {}; endpoint_metrics = endpoint_metrics or {}; cache = cache or {}
    health = supabase_health or {}; providers = provider_controls or {}; q = queue_contract(queue)
    tasks = {}

    verified = proof.get('verified') is True and proof.get('status') == 'PASS'
    tasks[201] = _task(201, 'PASS' if verified else 'NOT_VERIFIED', 'production-proof v2 is externally verified', critical=True)
    expected = deployment.get('expected_sha'); observed = deployment.get('deployed_sha')
    if expected and observed:
        s202 = 'PASS' if expected == observed else 'FAILED'
    else:
        s202 = 'NOT_VERIFIED'
    tasks[202] = _task(202, s202, 'deployed Railway SHA must exactly equal audited main SHA', critical=True,
                       evidence={'expected_sha': expected, 'deployed_sha': observed})
    tasks[203] = _task(203, 'PASS' if proof.get('proof_is_content_addressed') is True else 'NOT_VERIFIED',
                       'content-addressed external production proof', critical=True)
    checks = proof.get('checks') or {}
    digest_match = checks.get('digest_match')
    tasks[204] = _task(204, 'PASS' if digest_match is True else ('FAILED' if digest_match is False and proof.get('status') == 'FAILED' else 'NOT_VERIFIED'),
                       'critical-code changes invalidate stale proof', critical=True)

    state, detail = _latency_state(endpoint_metrics.get('cold_p95_ms'), COLD_ENDPOINT_BUDGET_MS, 'cold p95')
    tasks[205] = _task(205, state, detail, critical=True)
    state, detail = _latency_state(endpoint_metrics.get('hot_p95_ms'), HOT_ENDPOINT_BUDGET_MS, 'hot p95')
    tasks[206] = _task(206, state, detail)
    tasks[207] = _task(207, 'PASS' if cache.get('prewarm_enabled') is True else 'NOT_VERIFIED', 'cache prewarming enabled')
    tasks[208] = _task(208, 'PASS' if cache.get('async_refresh') is True else 'NOT_VERIFIED', 'cache refresh is asynchronous')
    tasks[209] = _task(209, 'PASS' if cache.get('stale_while_revalidate') is True else 'NOT_VERIFIED', 'last valid snapshot can be served during refresh')
    tasks[210] = _task(210, 'PASS' if cache.get('dependency_keys') else 'NOT_VERIFIED', 'dependency-scoped cache invalidation')
    tasks[211] = _task(211, 'PASS' if endpoint_metrics.get('profiled_stages') else 'NOT_VERIFIED', 'pipeline stage profiling is observable')
    budgets = endpoint_metrics.get('stage_budgets_ms') or {}
    tasks[212] = _task(212, 'PASS' if budgets and all(float(v) > 0 for v in budgets.values()) else 'NOT_VERIFIED', 'per-stage latency budgets configured')
    regression = endpoint_metrics.get('regression_pct')
    try:
        s213 = 'PASS' if float(regression) <= 20 else 'FAILED'
    except (TypeError, ValueError):
        s213 = 'NOT_VERIFIED'
    tasks[213] = _task(213, s213, 'latency regression <=20% versus accepted baseline')

    breaker_names = providers.get('circuit_breakers') or []
    tasks[214] = _task(214, 'PASS' if breaker_names else 'NOT_VERIFIED', 'provider-specific circuit breakers')
    tasks[215] = _task(215, 'PASS' if providers.get('bulkhead_isolation') is True else 'NOT_VERIFIED', 'provider bulkhead isolation')
    tasks[216] = _task(216, 'PASS' if q['durable'] and q['ack_after_remote_success'] else 'NOT_VERIFIED', 'durable failed-sync queue with remote-success ACK', critical=True)
    taxonomy_ok = all(classify_retry(k)['bounded'] for k in ('timeout','429','503','409','validation'))
    tasks[217] = _task(217, 'PASS' if taxonomy_ok else 'FAILED', 'bounded error-specific retry taxonomy')
    tasks[218] = _task(218, 'PASS' if q['dead_letter'] else 'NOT_VERIFIED', 'dead-letter queue for terminal sync failures')
    tasks[219] = _task(219, 'PASS' if providers.get('reconcile_after_recovery') is True else 'NOT_VERIFIED', 'automatic idempotent reconciliation after provider recovery')
    state, detail = _latency_state(roundtrip_ms, ROUNDTRIP_BUDGET_MS, 'Cloud↔Supabase roundtrip')
    tasks[220] = _task(220, state, detail, critical=True)

    generic_ok = health.get('status') == 'HEALTHY' and health.get('timeout_means_missing_data') is False
    if not generic_ok and tasks[220]['state'] == 'PASS':
        tasks[220] = _task(220, 'FAILED', 'roundtrip timing cannot pass while Supabase health is not fail-closed HEALTHY', critical=True)
    return {'status': 'PRE160_RESILIENCE_V7', 'tasks': {str(k): v for k, v in tasks.items()},
            'automatic_release': False, 'automatic_promotion': False, 'can_trade': False, 'real_trading': False}
