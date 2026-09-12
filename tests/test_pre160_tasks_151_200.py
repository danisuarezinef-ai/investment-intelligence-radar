from radar_pre160_controls_v6 import build_task_matrix, provider_divergence_guard, STATES


def _health():
    common = {
        'status': 'HEALTHY', 'configured': True, 'circuit_open': False,
        'circuit_remaining_seconds': 0.0, 'consecutive_failures': 0,
        'recoveries': 1, 'circuit_open_count': 1, 'last_latency_ms': 500.0,
        'timeout_means_missing_data': False,
        'cursors_advance_only_after_remote_success': True,
    }
    return {
        **common, 'max_batch': 250, 'all_configured_syncs_healthy': True,
        'learning_sync': {**common, 'max_batch': 250, 'last_latency_ms': 800.0},
    }


def _evidence():
    return {
        'status': 'PRE160_EVIDENCE_V3',
        'snapshot_hash': 'a' * 64,
        'freshness': {'status': 'FRESH'},
        'sample_gates': {'champion': {'status': 'MATURE'}, 'challenger': {'status': 'MATURE'}},
        'readiness_1_6': {'checks': {'runtime_30d': True}},
        'calibration': {'status': 'MATURE'},
        'multi_benchmark': {'status': 'AVAILABLE'},
        'cost_slippage': {'status': 'AVAILABLE'},
        'regime_horizon': {'matrix': [{'regime': 'bull', 'horizon': '1m', 'n': 8, 'mature': True}], 'blockers': []},
        'stress_readiness': {'status': 'AVAILABLE', 'observed_exposures': 2},
        'anti_overfitting_v2': {
            'score': 0.8,
            'components': {'live_forward': 0.7},
            'selection_uses_final_test': False,
            'selection_uses_live_forward': False,
        },
        'champion_degradation_sequential': {'automatic_demotion': False},
    }


def _hardening():
    return {
        'status': 'PRE160_EVIDENCE_V5',
        'snapshot_hash': 'b' * 64,
        'transactional_exact': 3,
        'ledger_fallback': 0,
        'provider_samples': [
            {'symbol': 'MSFT', 'asof': '2026-09-12T00:00:00Z', 'provider': 'p1', 'value': 100.00},
            {'symbol': 'MSFT', 'asof': '2026-09-12T00:00:00Z', 'provider': 'p2', 'value': 100.10},
        ],
        'envelope_source': {'remote_frozen': 3, 'local_candidates': 3},
        'decision_trace': {
            'status': 'COMPLETE', 'lookahead_flags': 0, 'ambiguous_keys': 0,
            'uses_exit_fields_for_entry_linkage': False, 'blockers': [],
            'rows': [{'provider_status': 'FRESH'}],
        },
    }


def _runtime():
    return {
        'champion_key': 'balanced',
        'scorecards': [
            {'competitor_key': 'balanced', 'family': 'balanced'},
            {'competitor_key': 'trend', 'family': 'trend'},
        ],
    }


def test_matrix_contains_exactly_50_tasks_and_valid_states():
    matrix = build_task_matrix(
        evidence=_evidence(), hardening=_hardening(), runtime=_runtime(),
        supabase_health=_health(), version='1.5.28', production_proof=False,
    )
    assert set(matrix['tasks']) == {str(i) for i in range(151, 201)}
    assert len(matrix['tasks']) == 50
    assert all(row['state'] in STATES for row in matrix['tasks'].values())
    assert matrix['tasks']['160']['state'] == 'NOT_VERIFIED'
    assert matrix['tasks']['200']['state'] == 'NOT_VERIFIED'
    assert matrix['tasks']['169']['state'] == 'PASS'
    assert matrix['tasks']['189']['state'] == 'PASS'
    assert matrix['automatic_release'] is False
    assert matrix['automatic_promotion'] is False
    assert matrix['automatic_demotion'] is False
    assert matrix['setup_allowed'] is False
    assert matrix['real_trading'] is False


def test_external_proof_can_only_close_160_and_200_without_changing_authority():
    matrix = build_task_matrix(
        evidence=_evidence(), hardening=_hardening(), runtime=_runtime(),
        supabase_health=_health(), version='1.5.28', production_proof=True,
    )
    assert matrix['tasks']['160']['state'] == 'PASS'
    assert matrix['tasks']['200']['state'] == 'PASS'
    assert all(row['state'] == 'PASS' for row in matrix['tasks'].values())
    assert matrix['setup_allowed'] is False
    assert matrix['can_trade'] is False
    assert matrix['real_trading'] is False


def test_immature_natural_evidence_remains_pending_not_fabricated():
    evidence = _evidence()
    evidence['sample_gates']['challenger'] = {'status': 'PENDING_SAMPLE'}
    evidence['readiness_1_6']['checks']['runtime_30d'] = False
    evidence['calibration'] = {'status': 'PENDING_SAMPLE'}
    evidence['stress_readiness'] = {'status': 'PENDING_SAMPLE', 'observed_exposures': 0}
    hardening = _hardening()
    hardening['transactional_exact'] = 0
    hardening['decision_trace']['status'] = 'EVIDENCE_PENDING'
    hardening['decision_trace']['blockers'] = ['NO_LINKED_PROSPECTIVE_CLOSES']
    matrix = build_task_matrix(
        evidence=evidence, hardening=hardening, runtime=_runtime(),
        supabase_health=_health(), production_proof=False,
    )
    assert matrix['tasks']['172']['state'] == 'PENDING_SAMPLE'
    assert matrix['tasks']['173']['state'] == 'PENDING_TIME'
    assert matrix['tasks']['174']['state'] == 'PENDING_SAMPLE'
    assert matrix['tasks']['178']['state'] == 'PENDING_SAMPLE'
    assert matrix['tasks']['180']['state'] == 'PENDING_SAMPLE'
    assert matrix['tasks']['183']['state'] == 'PENDING_SAMPLE'


def test_lookahead_collision_and_selection_leak_are_hard_failures():
    evidence = _evidence()
    evidence['anti_overfitting_v2']['selection_uses_final_test'] = True
    hardening = _hardening()
    hardening['decision_trace']['lookahead_flags'] = 1
    hardening['decision_trace']['ambiguous_keys'] = 2
    matrix = build_task_matrix(
        evidence=evidence, hardening=hardening, runtime=_runtime(),
        supabase_health=_health(), production_proof=False,
    )
    assert matrix['tasks']['164']['state'] == 'FAILED'
    assert matrix['tasks']['165']['state'] == 'FAILED'
    assert matrix['tasks']['170']['state'] == 'FAILED'
    assert matrix['tasks']['179']['state'] == 'FAILED'
    assert matrix['tasks']['180']['state'] == 'FAILED'
    assert matrix['tasks']['183']['state'] == 'FAILED'
    assert matrix['tasks']['186']['state'] == 'FAILED'


def test_provider_divergence_is_flagged_not_averaged_away():
    result = provider_divergence_guard([
        {'symbol': 'NVDA', 'asof': 't', 'provider': 'a', 'value': 100},
        {'symbol': 'NVDA', 'asof': 't', 'provider': 'b', 'value': 102},
    ], tolerance_bps=50)
    assert result['status'] == 'FAILED'
    assert len(result['violations']) == 1
    assert result['averaging_contradictions_allowed'] is False
    assert result['real_trading'] is False


def test_sync_circuit_open_never_reports_pass():
    health = _health()
    health['status'] = 'CIRCUIT_OPEN'
    health['circuit_open'] = True
    matrix = build_task_matrix(
        evidence=_evidence(), hardening=_hardening(), runtime=_runtime(),
        supabase_health=health, production_proof=False,
    )
    assert matrix['tasks']['152']['state'] == 'NOT_VERIFIED'
    assert matrix['tasks']['154']['state'] == 'NOT_VERIFIED'
    assert matrix['tasks']['196']['state'] == 'PASS'  # explicit aggregate is supplied by caller
