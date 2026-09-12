"""Pre-1.6 operational health, explicitly separate from investment quality.

This module is read-only. It scores transport/readiness infrastructure only and has no
input to ranking, portfolio allocation, model promotion, PAPER execution, or real trading.
Unknown/uninstrumented workers remain visible instead of being silently treated as healthy.
"""
from __future__ import annotations

REAL_TRADING = False


def _state_score(status):
    return {
        'HEALTHY': 100.0,
        'PASS': 100.0,
        'DEEP_READY': 100.0,
        'LITE_READY': 80.0,
        'LITE_READY_FAIL_CLOSED': 75.0,
        'STARTING': 65.0,
        'DEGRADED': 45.0,
        'CIRCUIT_OPEN': 25.0,
        'FAILED': 0.0,
        'NOT_CONFIGURED': 0.0,
        'NOT_VERIFIED': 50.0,
    }.get(str(status or '').upper(), 50.0)


def _sync_component(name, telemetry):
    t = telemetry if isinstance(telemetry, dict) else {}
    status = str(t.get('status') or 'NOT_VERIFIED')
    return {
        'name': name,
        'status': status,
        'score': _state_score(status),
        'configured': t.get('configured'),
        'successes': t.get('successes'),
        'terminal_failures': t.get('terminal_failures'),
        'consecutive_failures': t.get('consecutive_failures'),
        'last_latency_ms': t.get('last_latency_ms'),
        'timeout_seconds': t.get('default_timeout_seconds'),
        'circuit_open': t.get('circuit_open'),
    }


def operational_health(*, generic_sync=None, learning_sync=None, queue=None, provider=None,
                       readiness=None, partition=None):
    """Return an infrastructure-only score; investment_score_included is always False."""
    generic = _sync_component('generic_sync', generic_sync)
    learning = _sync_component('learning_sync', learning_sync)
    q = queue if isinstance(queue, dict) else {}
    p = provider if isinstance(provider, dict) else {}
    r = readiness if isinstance(readiness, dict) else {}
    part = partition if isinstance(partition, dict) else {}

    q_status = 'HEALTHY' if q.get('configured') is True and q.get('remote_stats_verified') is True else (
        'DEGRADED' if q.get('configured') is True else 'NOT_CONFIGURED')
    provider_status = 'HEALTHY' if p.get('wired') is True else 'NOT_VERIFIED'
    readiness_status = 'DEEP_READY' if r.get('deep_ready') is True else (
        'LITE_READY_FAIL_CLOSED' if r.get('lite_ready') is True else str(r.get('status') or 'NOT_VERIFIED'))
    partition_status = 'HEALTHY' if part.get('partitioned') is True and int(part.get('failed_cycles') or 0) == 0 else (
        'DEGRADED' if part.get('partitioned') is True else 'NOT_VERIFIED')

    components = [
        generic,
        learning,
        {'name':'durable_queue','status':q_status,'score':_state_score(q_status),
         'cross_redeploy_verified':q.get('cross_redeploy_verified'),
         'controlled_dlq_verified':q.get('controlled_dlq_verified'),
         'controlled_reprocess_verified':q.get('controlled_reprocess_verified')},
        {'name':'provider_transport','status':provider_status,'score':_state_score(provider_status),
         'controlled_probe':p.get('controlled_probe'),
         'external_failover_verified':p.get('failover_verified')},
        {'name':'tiered_readiness','status':readiness_status,'score':_state_score(readiness_status),
         'lite_ready':r.get('lite_ready'),'deep_ready':r.get('deep_ready')},
        {'name':'partitioned_sync','status':partition_status,'score':_state_score(partition_status),
         'completed_cycles':part.get('completed_cycles'),'failed_cycles':part.get('failed_cycles'),
         'backpressure_enqueued':part.get('backpressure_enqueued'),
         'backpressure_drained':part.get('backpressure_drained'),
         'backlog_last':part.get('backlog_last')},
    ]
    score = round(sum(float(x.get('score') or 0) for x in components) / len(components), 2)
    critical_failed = [x['name'] for x in components if x.get('status') in ('FAILED','NOT_CONFIGURED')]
    degraded = [x['name'] for x in components if x.get('status') in ('DEGRADED','CIRCUIT_OPEN')]
    if critical_failed:
        status = 'BLOCKED'
    elif degraded:
        status = 'DEGRADED'
    elif score >= 90:
        status = 'HEALTHY'
    else:
        status = 'OBSERVING'
    return {
        'status': status,
        'operational_score': score,
        'components': components,
        'critical_failed': critical_failed,
        'degraded': degraded,
        'investment_score_included': False,
        'affects_investment_ranking': False,
        'affects_model_promotion': False,
        'setup_allowed': False,
        'live_execution_allowed': False,
        'can_trade': False,
        'real_trading': False,
    }


def worker_utilization(*, generic_sync=None, learning_sync=None, partition=None, readiness=None,
                       queue=None, provider=None):
    """Expose only observed instrumentation; never invent utilization for legacy workers."""
    g = generic_sync if isinstance(generic_sync,dict) else {}
    l = learning_sync if isinstance(learning_sync,dict) else {}
    p = partition if isinstance(partition,dict) else {}
    r = readiness if isinstance(readiness,dict) else {}
    q = queue if isinstance(queue,dict) else {}
    pv = provider if isinstance(provider,dict) else {}
    workers = {
        'generic_supabase_sync': {
            'instrumentation':'OBSERVED', 'last_latency_ms':g.get('last_latency_ms'),
            'successes':g.get('successes'),'failures':g.get('terminal_failures'),
            'partition_cycle_ms':p.get('last_cycle_ms'),'backlog':p.get('backlog_last'),
        },
        'learning_sync': {
            'instrumentation':'OBSERVED','last_latency_ms':l.get('last_latency_ms'),
            'successes':l.get('successes'),'failures':l.get('terminal_failures'),
        },
        'pre160_deep_worker': {
            'instrumentation':'OBSERVED','status':r.get('status'),
            'profiler':r.get('profiler'),'scheduler':r.get('scheduler'),
        },
        'remote_retry_queue': {
            'instrumentation':'OBSERVED','requests':q.get('requests'),'successes':q.get('successes'),
            'failures':q.get('failures'),'last_latency_ms':q.get('last_latency_ms'),
        },
        'provider_transport_guard': {
            'instrumentation':'OBSERVED','providers':pv.get('providers'),'circuit':pv.get('circuit'),
            'rate_governor':pv.get('rate_governor'),
        },
        'closed_loop_paper': {'instrumentation':'NOT_INSTRUMENTED_FOR_CPU_UTILIZATION'},
        'autonomous_simulator': {'instrumentation':'NOT_INSTRUMENTED_FOR_CPU_UTILIZATION'},
        'persistent_authority': {'instrumentation':'NOT_INSTRUMENTED_FOR_CPU_UTILIZATION'},
        'forward_outcome_sync': {'instrumentation':'NOT_INSTRUMENTED_FOR_CPU_UTILIZATION'},
    }
    return {
        'status':'OBSERVED_WITH_GAPS',
        'workers':workers,
        'global_heavy_scheduler_required':False,
        'reason':'Deep evidence already serialized by DeepWorkScheduler; sync load is bounded/partitioned. Reconsider only if measured contention reappears.',
        'not_instrumented_is_not_zero':True,
        'real_trading':False,
    }
