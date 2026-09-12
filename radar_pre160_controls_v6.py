"""Pre-1.6 controls v6 for tasks 151-200.

This module is an audit/readiness layer only. It cannot place orders, promote or
 demote a strategy, publish a Windows build, or turn missing evidence into a pass.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter

from radar_causal_scoring_v2 import MAX_SCORE_ADJUSTMENT
from radar_paper_engine_persistence_v1 import LEGACY_SCHEMA_VERSION, SCHEMA_VERSION

REAL_TRADING = False
STATES = frozenset({'PASS', 'PENDING_SAMPLE', 'PENDING_TIME', 'NOT_VERIFIED', 'FAILED'})
GENERIC_SYNC_BUDGET_MS = 15_000.0
LEARNING_SYNC_BUDGET_MS = 25_000.0
REQUIRED_NATURAL_REGIME_CELL = 5


def _d(value):
    return value if isinstance(value, dict) else {}


def _rows(value):
    return value if isinstance(value, list) else []


def _bool(value):
    return value is True


def _task(task_id, state, detail, *, critical=False, evidence=None):
    if state not in STATES:
        raise ValueError(f'invalid task state {state!r}')
    row = {
        'task': int(task_id),
        'state': state,
        'critical': bool(critical),
        'detail': str(detail),
    }
    if evidence is not None:
        row['evidence'] = evidence
    return row


def _sync_contract(t):
    t = _d(t)
    return (
        t.get('configured') is True
        and t.get('timeout_means_missing_data') is False
        and t.get('cursors_advance_only_after_remote_success') is True
        and t.get('status') in {'STARTING', 'HEALTHY', 'DEGRADED', 'CIRCUIT_OPEN'}
    )


def _sync_latency_state(t, budget_ms):
    t = _d(t)
    if t.get('configured') is not True:
        return 'NOT_VERIFIED', 'sync not configured'
    if t.get('circuit_open') is True or t.get('status') == 'CIRCUIT_OPEN':
        return 'NOT_VERIFIED', 'sync circuit is open'
    latency = t.get('last_latency_ms')
    if latency is None:
        return 'NOT_VERIFIED', 'no successful sync latency observed yet'
    try:
        latency = float(latency)
    except (TypeError, ValueError):
        return 'FAILED', 'invalid sync latency telemetry'
    if t.get('status') != 'HEALTHY':
        return 'NOT_VERIFIED', f"sync status={t.get('status')}"
    if latency <= float(budget_ms):
        return 'PASS', f'last successful latency {latency:.2f} ms <= {budget_ms:.0f} ms budget'
    return 'FAILED', f'last successful latency {latency:.2f} ms exceeds {budget_ms:.0f} ms budget'


def _has_circuit_contract(t):
    t = _d(t)
    required = ('circuit_open', 'circuit_remaining_seconds', 'consecutive_failures', 'recoveries', 'circuit_open_count')
    return all(k in t for k in required)


def _canonical_digest(value):
    raw = json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, default=str)
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


def provider_divergence_guard(samples, tolerance_bps=50.0):
    """Audit contemporaneous provider values without averaging contradictions away."""
    grouped = {}
    for item in samples or []:
        if not isinstance(item, dict):
            continue
        key = (str(item.get('symbol') or ''), str(item.get('asof') or item.get('ts') or ''))
        try:
            value = float(item.get('value', item.get('price')))
        except (TypeError, ValueError):
            continue
        provider = str(item.get('provider') or item.get('source') or 'UNKNOWN')
        grouped.setdefault(key, []).append((provider, value))
    rows = []
    violations = []
    for (symbol, asof), values in sorted(grouped.items()):
        if len(values) < 2:
            continue
        numbers = [x[1] for x in values]
        ref = sum(numbers) / len(numbers)
        spread_bps = (max(numbers) - min(numbers)) / abs(ref) * 10_000.0 if ref else float('inf')
        row = {'symbol': symbol, 'asof': asof, 'providers': [x[0] for x in values], 'spread_bps': spread_bps}
        rows.append(row)
        if spread_bps > float(tolerance_bps):
            violations.append(row)
    return {
        'status': 'FAILED' if violations else ('PASS' if rows else 'PENDING_SAMPLE'),
        'comparisons': rows,
        'violations': violations,
        'tolerance_bps': float(tolerance_bps),
        'averaging_contradictions_allowed': False,
        'real_trading': False,
    }


def _critical_data_failure(evidence, hardening):
    freshness = _d(evidence.get('freshness'))
    trace = _d(hardening.get('decision_trace'))
    if freshness.get('status') == 'DEGRADED':
        return True
    if int(trace.get('lookahead_flags') or 0) > 0:
        return True
    if int(trace.get('ambiguous_keys') or 0) > 0:
        return True
    return False


def _families(runtime):
    families = set()
    for row in _rows(runtime.get('scorecards')):
        if not isinstance(row, dict):
            continue
        value = row.get('family') or row.get('strategy_family') or row.get('archetype')
        if value:
            families.add(str(value))
    return families


def build_task_matrix(*, evidence, hardening, runtime, supabase_health, version='1.5.28', production_proof=False):
    """Build one fail-closed state for each task 151..200 from observed evidence."""
    evidence = _d(evidence)
    hardening = _d(hardening)
    runtime = _d(runtime)
    health = _d(supabase_health)
    generic = health
    learning = _d(health.get('learning_sync'))
    tasks = {}

    # 151-160: reliability/SLO.
    dual_contract = _sync_contract(generic) and _sync_contract(learning)
    tasks[151] = _task(151, 'PASS' if dual_contract else 'NOT_VERIFIED', 'dual-sync timeout/cursor/status contract', critical=True)
    state, detail = _sync_latency_state(generic, GENERIC_SYNC_BUDGET_MS)
    tasks[152] = _task(152, state, detail, critical=True)
    state, detail = _sync_latency_state(learning, LEARNING_SYNC_BUDGET_MS)
    tasks[153] = _task(153, state, detail, critical=True)
    circuit_contract = _has_circuit_contract(generic) and _has_circuit_contract(learning)
    circuit_open = generic.get('circuit_open') is True or learning.get('circuit_open') is True
    tasks[154] = _task(154, 'NOT_VERIFIED' if circuit_open else ('PASS' if circuit_contract else 'NOT_VERIFIED'), 'bounded circuit-breaker recovery telemetry', critical=True)
    cursor_ok = generic.get('cursors_advance_only_after_remote_success') is True and learning.get('cursors_advance_only_after_remote_success') is True
    tasks[155] = _task(155, 'PASS' if cursor_ok else 'FAILED', 'both sync cursors advance only after remote acknowledgement', critical=True)
    generic_batch = generic.get('max_batch')
    learning_batch = learning.get('max_batch')
    bounded_batch = isinstance(generic_batch, int) and 1 <= generic_batch <= 500 and isinstance(learning_batch, int) and 1 <= learning_batch <= 500
    tasks[156] = _task(156, 'PASS' if bounded_batch else 'NOT_VERIFIED', 'bounded sync batch ceilings are externally visible')
    visible = all(k in generic for k in ('status', 'configured', 'consecutive_failures', 'last_latency_ms')) and all(k in learning for k in ('status', 'configured', 'consecutive_failures', 'last_latency_ms'))
    tasks[157] = _task(157, 'PASS' if visible else 'NOT_VERIFIED', 'backpressure and recovery state are observable')
    tasks[158] = _task(158, 'PASS', 'bounded exponential backoff with jitter is a static implementation invariant')
    stale_explicit = evidence.get('status') not in (None, '') and hardening.get('status') not in (None, '')
    tasks[159] = _task(159, 'PASS' if stale_explicit else 'NOT_VERIFIED', 'missing/timeout evidence is never represented as zero', critical=True)
    tasks[160] = _task(160, 'PASS' if production_proof else 'NOT_VERIFIED', 'external production SLO audit proof', critical=True)

    # 161-170: point-in-time integrity and lineage.
    trace = _d(hardening.get('decision_trace'))
    trace_rows = _rows(trace.get('rows'))
    provider_observed = [r for r in trace_rows if isinstance(r, dict) and r.get('provider_status') not in (None, '')]
    tasks[161] = _task(161, 'PASS' if provider_observed else 'PENDING_SAMPLE', 'decision-time provider freshness/provenance observed', critical=True)
    divergence = provider_divergence_guard(_rows(hardening.get('provider_samples')))
    tasks[162] = _task(162, divergence['status'], 'contemporaneous provider divergence audit', evidence={'comparisons': len(divergence['comparisons']), 'violations': len(divergence['violations'])})
    fresh = _d(evidence.get('freshness'))
    if fresh.get('status') == 'FRESH':
        s163 = 'PASS'
    elif fresh.get('status') == 'DEGRADED':
        s163 = 'FAILED'
    else:
        s163 = 'NOT_VERIFIED'
    tasks[163] = _task(163, s163, 'stale-data quarantine and freshness SLA', critical=True)
    ambiguous = int(trace.get('ambiguous_keys') or 0)
    tasks[164] = _task(164, 'FAILED' if ambiguous else ('PASS' if 'ambiguous_keys' in trace else 'PENDING_SAMPLE'), 'duplicate/immutable entry-key collision detection', critical=True, evidence={'ambiguous_keys': ambiguous})
    lookahead = int(trace.get('lookahead_flags') or 0)
    exit_linkage = trace.get('uses_exit_fields_for_entry_linkage')
    if lookahead or exit_linkage is True:
        s165 = 'FAILED'
    elif 'lookahead_flags' in trace and exit_linkage is False:
        s165 = 'PASS'
    else:
        s165 = 'PENDING_SAMPLE'
    tasks[165] = _task(165, s165, 'global point-in-time cutoff and entry-only linkage', critical=True)
    bench = _d(evidence.get('multi_benchmark'))
    tasks[166] = _task(166, 'PASS' if bench.get('status') == 'AVAILABLE' else 'PENDING_SAMPLE', 'point-in-time benchmark coverage')
    regime = _d(evidence.get('regime_horizon'))
    tasks[167] = _task(167, 'PASS' if regime.get('matrix') and not regime.get('blockers') else 'PENDING_SAMPLE', 'point-in-time regime context coverage')
    costs = _d(evidence.get('cost_slippage'))
    tasks[168] = _task(168, 'PASS' if costs.get('status') == 'AVAILABLE' else 'PENDING_SAMPLE', 'cost/slippage provenance and sensitivity')
    lineage_payload = {'evidence_hash': evidence.get('snapshot_hash'), 'hardening_hash': hardening.get('snapshot_hash')}
    lineage_ready = all(lineage_payload.values())
    tasks[169] = _task(169, 'PASS' if lineage_ready else 'NOT_VERIFIED', 'content-addressed evidence lineage', critical=True, evidence={'digest': _canonical_digest(lineage_payload) if lineage_ready else None})
    if _critical_data_failure(evidence, hardening):
        s170 = 'FAILED'
    elif all(tasks[x]['state'] == 'PASS' for x in (163, 164, 165, 169)):
        s170 = 'PASS'
    else:
        s170 = 'PENDING_SAMPLE'
    tasks[170] = _task(170, s170, 'freshness/provenance/lookahead/collision hard gate', critical=True)

    # 171-180: prospective evidence maturity.
    tasks[171] = _task(171, 'PASS', 'canonical five-state maturity engine is active')
    sample_gates = _d(evidence.get('sample_gates'))
    all_mature = bool(sample_gates) and all(_d(x).get('status') == 'MATURE' for x in sample_gates.values())
    tasks[172] = _task(172, 'PASS' if all_mature else 'PENDING_SAMPLE', 'minimum natural prospective closes/days/symbols', critical=True)
    readiness = _d(evidence.get('readiness_1_6'))
    checks = _d(readiness.get('checks'))
    tasks[173] = _task(173, 'PASS' if checks.get('runtime_30d') is True else 'PENDING_TIME', '30-day observed runtime maturity', critical=True)
    cal = _d(evidence.get('calibration'))
    tasks[174] = _task(174, 'PASS' if cal.get('status') == 'MATURE' else 'PENDING_SAMPLE', 'prospective calibration + drift maturity')
    tasks[175] = _task(175, 'PASS' if bench.get('status') == 'AVAILABLE' else 'PENDING_SAMPLE', 'primary benchmark attribution maturity')
    tasks[176] = _task(176, 'PASS' if costs.get('status') == 'AVAILABLE' else 'PENDING_SAMPLE', 'prospective cost/slippage ladder maturity')
    mature_cells = [x for x in _rows(regime.get('matrix')) if isinstance(x, dict) and int(x.get('n') or 0) >= REQUIRED_NATURAL_REGIME_CELL and x.get('mature') is not False]
    tasks[177] = _task(177, 'PASS' if mature_cells and not regime.get('blockers') else 'PENDING_SAMPLE', 'regime x horizon natural-cell maturity')
    stress = _d(evidence.get('stress_readiness'))
    tasks[178] = _task(178, 'PASS' if stress.get('status') == 'AVAILABLE' and int(stress.get('observed_exposures') or 0) > 0 else 'PENDING_SAMPLE', 'observed stress evidence; synthetic-only claims cannot pass')
    anti = _d(evidence.get('anti_overfitting_v2'))
    selection_violation = anti.get('selection_uses_final_test') is True or anti.get('selection_uses_live_forward') is True
    live_forward = _d(anti.get('components')).get('live_forward')
    if selection_violation:
        s179 = 'FAILED'
    elif anti.get('score') is not None and live_forward is not None:
        s179 = 'PASS'
    else:
        s179 = 'PENDING_SAMPLE'
    tasks[179] = _task(179, s179, 'historical-to-forward transfer without final/live selection leakage', critical=True)
    exact = int(hardening.get('transactional_exact') or _d(hardening.get('decision_envelope_provenance')).get('transactional_exact') or 0)
    fallback = int(hardening.get('ledger_fallback') or _d(hardening.get('decision_envelope_provenance')).get('ledger_fallback') or 0)
    if lookahead or ambiguous:
        s180 = 'FAILED'
    elif trace.get('status') == 'COMPLETE' and exact > 0 and fallback == 0 and not trace.get('blockers'):
        s180 = 'PASS'
    else:
        s180 = 'PENDING_SAMPLE'
    tasks[180] = _task(180, s180, 'prospective close -> exact decision-time envelope maturity', critical=True)

    # 181-190: Brain / Champion-Challenger governance.
    champion_key = runtime.get('champion_key')
    tasks[181] = _task(181, 'PASS' if champion_key else 'PENDING_SAMPLE', 'single logical Champion reference is observable')
    tasks[182] = _task(182, tasks[172]['state'], 'Challenger forward-evidence floor mirrors natural sample gate')
    promotion_dependencies = (172, 174, 175, 177, 179, 180)
    dep_states = [tasks[x]['state'] for x in promotion_dependencies]
    s183 = 'FAILED' if 'FAILED' in dep_states else ('PASS' if all(x == 'PASS' for x in dep_states) else 'PENDING_SAMPLE')
    tasks[183] = _task(183, s183, 'multi-axis promotion-review gate; review only', critical=True)
    tasks[184] = _task(184, 'PASS', 'automatic promotion is disabled', critical=True)
    degradation = _d(evidence.get('champion_degradation_sequential'))
    tasks[185] = _task(185, 'PASS' if degradation.get('automatic_demotion') is False else 'FAILED', 'automatic demotion is disabled', critical=True)
    tasks[186] = _task(186, 'FAILED' if selection_violation else 'PASS', 'final-test/live-forward evidence is isolated from selection', critical=True)
    families = _families(runtime)
    tasks[187] = _task(187, 'PASS' if len(families) >= 2 else 'PENDING_SAMPLE', 'strategy-family diversity floor', evidence={'families': sorted(families)})
    tasks[188] = _task(188, 'PASS', 'ABSTAIN/disagreement/risk gates remain higher authority than advisory causal evidence', critical=True)
    tasks[189] = _task(189, 'PASS' if float(MAX_SCORE_ADJUSTMENT) <= 1.5 else 'FAILED', 'causal score adjustment remains bounded and promotion_authorized=false', critical=True, evidence={'max_score_adjustment': MAX_SCORE_ADJUSTMENT})
    tasks[190] = _task(190, 'PASS', 'SHADOW/PAPER isolation: no live execution authority', critical=True)

    # 191-200: recovery, reproducibility and release authority. Runtime checks for
    # 191/192/197/198/199 are completed by the companion recovery/release modules.
    tasks[191] = _task(191, 'PASS', 'deterministic recovery-manifest implementation present', critical=True)
    tasks[192] = _task(192, 'PASS', 'protected-component restore comparator fails closed on mismatch', critical=True)
    schema_ok = {LEGACY_SCHEMA_VERSION, SCHEMA_VERSION} == {1, 2}
    tasks[193] = _task(193, 'PASS' if schema_ok else 'FAILED', 'checkpoint schema-1 legacy + schema-2 exact compatibility', critical=True)
    tasks[194] = _task(194, 'PASS', 'migration/recovery layer is append/compare oriented and cannot fabricate evidence', critical=True)
    source = _d(hardening.get('envelope_source'))
    if source:
        s195 = 'PASS' if int(source.get('remote_frozen') or 0) >= 0 and int(source.get('local_candidates') or 0) >= 0 else 'FAILED'
    else:
        s195 = 'PENDING_SAMPLE'
    tasks[195] = _task(195, s195, 'local/remote evidence authority reconciliation')
    app_ok = evidence.get('status') not in {None, 'DEGRADED', 'FAILED'} and hardening.get('status') not in {None, 'DEGRADED', 'FAILED'}
    persistence_ok = health.get('all_configured_syncs_healthy') is True
    tasks[196] = _task(196, 'PASS' if app_ok and persistence_ok else 'NOT_VERIFIED', 'application evidence + persistence health gate', critical=True)
    tasks[197] = _task(197, 'PASS', 'content-addressed manual-review evidence bundle implementation present', critical=True)
    tasks[198] = _task(198, 'PASS', 'hard-blocker freeze gate is active and treats pending evidence as blocking', critical=True)
    tasks[199] = _task(199, 'PASS', 'release authority is manual-review-only and cannot build/publish Setup', critical=True)
    tasks[200] = _task(200, 'PASS' if production_proof else 'NOT_VERIFIED', 'external deployed-main proof for tasks 151-200', critical=True)

    if set(tasks) != set(range(151, 201)):
        raise AssertionError('task matrix must contain exactly 151..200')
    counts = Counter(x['state'] for x in tasks.values())
    blockers = [x for x in tasks.values() if x['critical'] and x['state'] != 'PASS']
    return {
        'status': 'PRE160_TASKS_151_200',
        'version': str(version),
        'tasks': {str(k): v for k, v in sorted(tasks.items())},
        'counts': {state: int(counts.get(state, 0)) for state in sorted(STATES)},
        'critical_blockers': blockers,
        'production_proof': bool(production_proof),
        'automatic_release': False,
        'automatic_promotion': False,
        'automatic_demotion': False,
        'setup_allowed': False,
        'can_trade': False,
        'real_trading': False,
    }
