"""Pre-1.6 task matrix for tasks 271-310.

States are evidence-derived. Implemented code is not automatically PASS.
"""
from __future__ import annotations

import time

REAL_TRADING = False
STATES = {'PASS', 'PENDING_SAMPLE', 'PENDING_TIME', 'NOT_VERIFIED', 'FAILED'}


def _task(task_id, state, detail, *, critical=False, evidence=None):
    if state not in STATES:
        raise ValueError(state)
    out = {'task': int(task_id), 'state': state, 'detail': detail, 'critical': bool(critical)}
    if evidence is not None:
        out['evidence'] = evidence
    return out


def _bool_state(value, *, false_state='NOT_VERIFIED'):
    if value is True:
        return 'PASS'
    if value is False:
        return false_state
    return 'NOT_VERIFIED'


def _latency_state(value, budget):
    if not isinstance(value, (int, float)):
        return 'NOT_VERIFIED'
    return 'PASS' if float(value) <= float(budget) else 'FAILED'


def build_matrix_271_310(*, readiness, queue, provider, generic_sync, learning_sync, proof_v3,
                         deployment=None, ci_evidence=None, prior_gate=None):
    readiness = readiness or {}; queue = queue or {}; provider = provider or {}
    generic = generic_sync or {}; learning = learning_sync or {}; proof = proof_v3 or {}
    deployment = deployment or {}; ci = ci_evidence or {}; prior_gate = prior_gate or {}
    tasks = {}

    # 271-280: tiered readiness and SLO
    tasks[271] = _task(271, _bool_state(readiness.get('lite_ready')), 'tiered light snapshot is immediately available', critical=True)
    tasks[272] = _task(272, 'PASS' if readiness.get('status') in {'WARMING','LITE_READY','DEEP_READY','DEGRADED','FAILED'} else 'FAILED', 'formal readiness state machine')
    prof = readiness.get('profiler') or {}; stages = prof.get('stages') or {}
    tasks[273] = _task(273, 'PASS' if stages.get('deep_total',{}).get('samples',0) > 0 else 'NOT_VERIFIED', 'deep snapshot stage profiler has empirical samples', critical=True, evidence=stages)
    tasks[274] = _task(274, _bool_state(readiness.get('shared_deep_snapshot')), 'deep evidence is computed once then shared by v7 surfaces')
    tasks[275] = _task(275, _bool_state(readiness.get('dependency_token_cache')), 'dependency-token cache invalidates only changed dependencies')
    sched = readiness.get('scheduler') or {}
    tasks[276] = _task(276, 'PASS' if sched.get('serialized_deep_work') is True else 'NOT_VERIFIED', 'deep prewarm scheduling prevents overlap')
    tasks[277] = _task(277, 'PASS' if sched.get('cpu_io_budget_policy') == 'ONE_DEEP_JOB_AT_A_TIME' else 'NOT_VERIFIED', 'explicit CPU/I/O maintenance budget')
    budgets = readiness.get('budgets_ms') or {}; http = stages.get('http_v7') or {}
    tasks[278] = _task(278, _latency_state(http.get('p95_ms'), budgets.get('cold_http',1000)), 'empirical cold HTTP SLO', critical=True, evidence=http)
    enough_hot = int(http.get('samples') or 0) >= 5
    hot_state = _latency_state(http.get('p95_ms'), budgets.get('hot_http',250)) if enough_hot else 'PENDING_SAMPLE'
    tasks[279] = _task(279, hot_state, 'p50/p95/p99 hot-path latency with >=5 samples', evidence=http)
    regression = ci.get('latency_regression_pct')
    tasks[280] = _task(280, 'NOT_VERIFIED' if regression is None else ('PASS' if float(regression) <= 20 else 'FAILED'), 'latency regression gate <=20% versus accepted baseline')

    # 281-290: remote durability
    tasks[281] = _task(281, 'PASS' if queue.get('durable_backend') == 'SUPABASE' and queue.get('configured') else 'NOT_VERIFIED', 'retry queue uses remote durable backend', critical=True)
    tasks[282] = _task(282, 'PASS' if queue.get('remote_stats_verified') is True else 'NOT_VERIFIED', 'application path reaches Supabase retry queue', critical=True)
    tasks[283] = _task(283, 'PASS' if queue.get('dead_letter_remote') is True and queue.get('remote_stats_verified') is True else 'NOT_VERIFIED', 'dead-letter queue is remotely persisted')
    tasks[284] = _task(284, 'PASS' if queue.get('ack_after_remote_success') is True else 'FAILED', 'ACK occurs only after caller confirms remote success')
    tasks[285] = _task(285, 'PASS' if ci.get('crash_restart_test') is True else 'NOT_VERIFIED', 'crash/restart test preserves unacked work')
    tasks[286] = _task(286, 'PASS' if ci.get('duplicate_delivery_test') is True else 'NOT_VERIFIED', 'duplicate delivery remains idempotent')
    tasks[287] = _task(287, 'PASS' if ci.get('outage_recovery_test') is True else 'NOT_VERIFIED', 'Supabase/provider outage and recovery simulated fail-closed')
    tasks[288] = _task(288, 'PASS' if ci.get('queue_saturation_test') is True else 'NOT_VERIFIED', 'queue saturation/backpressure protection')
    tasks[289] = _task(289, 'PASS' if ci.get('poison_message_test') is True else 'NOT_VERIFIED', 'poison message isolation does not block later items')
    tasks[290] = _task(290, 'PASS' if queue.get('cross_redeploy_verified') is True else 'PENDING_TIME', 'remote probe survived a distinct Railway deployment identity', critical=True,
                       evidence={'previous_deployment':queue.get('previous_deployment'),'current_deployment':queue.get('current_deployment')})

    # 291-300: provider resilience
    tasks[291] = _task(291, 'PASS' if provider.get('wired') is True and provider.get('bulkhead_isolation') is True else 'NOT_VERIFIED', 'provider bulkheads are wired to a production transport path')
    circuit = provider.get('circuit') or {}
    tasks[292] = _task(292, 'PASS' if circuit.get('state_machine') == 'CLOSED_OPEN_HALF_OPEN' else 'NOT_VERIFIED', 'explicit CLOSED/OPEN/HALF_OPEN circuit state machine')
    tasks[293] = _task(293, 'PASS' if provider.get('failover_verified') is True else 'PENDING_SAMPLE', 'provider failover requires two independently verified live sources')
    rate = provider.get('rate_governor') or {}
    tasks[294] = _task(294, 'PASS' if rate.get('adaptive_rate_governor') is True else 'NOT_VERIFIED', '429/timeout adaptive rate governor')
    recent_timeout = generic.get('last_error_type') in {'TimeoutError','URLError'} or learning.get('last_error_type') in {'TimeoutError','URLError'}
    both_configured = generic.get('configured') is True and learning.get('configured') is True
    tasks[295] = _task(295, 'PASS' if both_configured and not recent_timeout and generic.get('timeout_means_missing_data') is False and learning.get('timeout_means_missing_data') is False else 'NOT_VERIFIED', 'Supabase timeouts are bounded and never converted to missing/zero evidence', critical=True)
    dual_healthy = generic.get('status') == 'HEALTHY' and learning.get('status') == 'HEALTHY'
    tasks[296] = _task(296, 'PASS' if dual_healthy else 'NOT_VERIFIED', 'generic and learning sync health are independently healthy', critical=True)
    empirical = dual_healthy and int(generic.get('successes') or 0) >= 3 and int(learning.get('successes') or 0) >= 3
    tasks[297] = _task(297, 'PASS' if empirical else 'PENDING_SAMPLE', 'dual-channel empirical success/latency SLO has sufficient runtime samples')
    tasks[298] = _task(298, 'PASS' if provider.get('reconcile_after_recovery') is True else 'NOT_VERIFIED', 'idempotent remote compare is wired after recovery')
    tasks[299] = _task(299, 'PASS' if ci.get('network_partition_test') is True else 'NOT_VERIFIED', 'partial network partition/reconnect test')
    critical_281_299 = [tasks[i] for i in range(281,300) if tasks[i].get('critical')]
    resilience_ok = all(x['state']=='PASS' for x in critical_281_299)
    tasks[300] = _task(300, 'PASS' if resilience_ok else 'NOT_VERIFIED', 'resilience gate requires every critical durability/sync control', critical=True)

    # 301-310: production proof v3 and master gate
    contract = proof.get('contract') or {}
    tasks[301] = _task(301, 'PASS' if contract.get('derived_not_asserted') is True else 'NOT_VERIFIED', 'production proof v3 derives checks from observations')
    exact = bool(deployment.get('expected_sha')) and deployment.get('expected_sha') == deployment.get('deployed_sha')
    digest_ok = proof.get('derived_checks',{}).get('digest_match') is True
    tasks[302] = _task(302, 'PASS' if exact and digest_ok else 'NOT_VERIFIED', 'exact GitHub SHA + Railway SHA + protected digest', critical=True,
                       evidence={'expected_sha':deployment.get('expected_sha'),'deployed_sha':deployment.get('deployed_sha')})
    dchecks = proof.get('derived_checks') or {}
    tasks[303] = _task(303, 'PASS' if dchecks.get('tasks_151_200') is True else 'NOT_VERIFIED', '151-200 verified in the same external proof run')
    tasks[304] = _task(304, 'PASS' if dchecks.get('tasks_201_270') is True else 'NOT_VERIFIED', '201-270 verified from a ready source in the same external proof run')
    tasks[305] = _task(305, 'PASS' if dchecks.get('dual_sync') is True else 'NOT_VERIFIED', 'dual-sync proof is measured, not asserted', critical=True)
    tasks[306] = _task(306, 'PASS' if proof.get('no_self_certification') is True and contract.get('runtime_can_approve_proof') is False else 'NOT_VERIFIED', 'runtime cannot self-certify production')
    tasks[307] = _task(307, 'PASS' if ci.get('tamper_test') is True else 'NOT_VERIFIED', 'protected-file tamper invalidates digest')
    tasks[308] = _task(308, 'PASS' if ci.get('stale_deployment_test') is True else 'NOT_VERIFIED', 'stale Railway SHA causes audit failure')
    tasks[309] = _task(309, 'PASS' if ci.get('failed_audit_propagation') is True else 'NOT_VERIFIED', 'failed audit cannot release/promote')
    critical = [tasks[i] for i in range(271,310) if tasks[i].get('critical')]
    upstream_blocked = prior_gate.get('status') not in (None, 'READY_FOR_MANUAL_1_6_REVIEW')
    master_ready = all(x['state']=='PASS' for x in critical) and proof.get('verified') is True and not upstream_blocked
    tasks[310] = _task(310, 'PASS', 'master gate v4 is reproducible; current release verdict remains manual and fail-closed', critical=True,
                       evidence={'release_verdict':'READY_FOR_MANUAL_1_6_REVIEW' if master_ready else 'BLOCKED_PRE160'})

    out = {str(i): tasks[i] for i in range(271,311)}
    failed = [k for k,v in out.items() if v.get('critical') and v.get('state')=='FAILED']
    pending = [k for k,v in out.items() if v.get('critical') and v.get('state')!='PASS']
    return {
        'status': 'PRE160_TASKS_271_310',
        'tasks': out,
        'critical_failed': failed,
        'critical_pending': pending,
        'master_gate_v4': {
            'status': 'READY_FOR_MANUAL_1_6_REVIEW' if master_ready else 'BLOCKED_PRE160',
            'manual_review_only': True,
            'setup_allowed': False,
            'automatic_release': False,
            'automatic_promotion': False,
            'automatic_demotion': False,
            'live_execution_allowed': False,
            'can_trade': False,
            'real_trading': False,
        },
        'observed_at_epoch': time.time(),
        'stable_windows_version': '1.5.28',
        'candidate_version': '1.6.0',
        'setup_allowed': False,
        'setup_built': False,
        'automatic_release': False,
        'can_trade': False,
        'real_trading': False,
    }
