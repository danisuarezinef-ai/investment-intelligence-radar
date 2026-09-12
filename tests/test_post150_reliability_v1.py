import cloud_service_v5 as v5


def test_readiness_board_separates_time_sample_and_pass(monkeypatch):
    monkeypatch.setattr(v5.base4, 'pre160_evidence_cached', lambda: {
        'status': 'PRE160_EVIDENCE',
        'readiness_1_6': {
            'status': 'BLOCKED_PRE160',
            'score_pct': 30.0,
            'checks': {
                'runtime_30d': False,
                'benchmark_coverage': True,
                'calibration_mature': False,
            },
            'blockers': [],
        },
    })
    monkeypatch.setattr(v5.base4, 'pre160_hardening_cached', lambda: {
        'readiness_countdown': {'status': 'CONDITIONAL_WAIT'},
    })
    monkeypatch.setattr(v5.base4, 'tasks_131_150_cached', lambda: {
        'transactional_exact': 0,
        'decision_trace': {'status': 'EVIDENCE_PENDING', 'blockers': ['NO_LINKED_PROSPECTIVE_CLOSES']},
    })
    monkeypatch.setattr(v5, 'sync_telemetry', lambda: {'status': 'HEALTHY', 'real_trading': False})

    board = v5.readiness_board()
    states = {row['check']: row['state'] for row in board['checks']}
    assert states['runtime_30d'] == 'PENDING_TIME'
    assert states['benchmark_coverage'] == 'PASS'
    assert states['calibration_mature'] == 'PENDING_SAMPLE'
    assert board['task_150']['state'] == 'PENDING_SAMPLE'
    assert board['setup_allowed'] is False
    assert board['real_trading'] is False


def test_readiness_degraded_never_claims_pass(monkeypatch):
    monkeypatch.setattr(v5.base4, 'pre160_evidence_cached', lambda: {
        'status': 'DEGRADED',
        'readiness_1_6': {'checks': {'benchmark_coverage': True}},
    })
    monkeypatch.setattr(v5.base4, 'pre160_hardening_cached', lambda: {})
    monkeypatch.setattr(v5.base4, 'tasks_131_150_cached', lambda: {'decision_trace': {}})
    monkeypatch.setattr(v5, 'sync_telemetry', lambda: {'status': 'DEGRADED', 'real_trading': False})
    board = v5.readiness_board()
    assert board['checks'][0]['state'] == 'NOT_VERIFIED'
    assert board['real_trading'] is False


def test_provenance_endpoint_preserves_pending_evidence(monkeypatch):
    monkeypatch.setattr(v5.base4, 'tasks_131_150_cached', lambda: {
        'transactional_exact': 0,
        'ledger_fallback': 0,
        'strategy_versions_missing': 0,
        'envelope_source': {'status': 'EVIDENCE_PENDING'},
        'decision_trace': {
            'status': 'EVIDENCE_PENDING',
            'linkage': 'competitor+symbol+entry_ts',
            'uses_exit_fields_for_entry_linkage': False,
            'blockers': ['NO_LINKED_PROSPECTIVE_CLOSES'],
        },
        'blockers': ['NO_TRANSACTIONAL_ENVELOPE_OBSERVED_YET'],
    })
    payload = v5.decision_provenance_status()
    assert payload['status'] == 'EVIDENCE_PENDING'
    assert payload['transactional_exact'] == 0
    assert payload['entry_linkage'] == 'competitor+symbol+entry_ts'
    assert payload['uses_exit_fields_for_entry_linkage'] is False
    assert payload['natural_evidence_only'] is True
    assert payload['backfill_allowed'] is False
    assert payload['real_trading'] is False


def test_task150_can_only_pass_with_observed_envelope_and_closed_trace(monkeypatch):
    monkeypatch.setattr(v5.base4, 'pre160_evidence_cached', lambda: {
        'status': 'PRE160_EVIDENCE', 'readiness_1_6': {'checks': {}}
    })
    monkeypatch.setattr(v5.base4, 'pre160_hardening_cached', lambda: {})
    monkeypatch.setattr(v5.base4, 'tasks_131_150_cached', lambda: {
        'transactional_exact': 1,
        'decision_trace': {'status': 'VERIFIED', 'blockers': []},
    })
    monkeypatch.setattr(v5, 'sync_telemetry', lambda: {'status': 'HEALTHY', 'real_trading': False})
    assert v5.readiness_board()['task_150']['state'] == 'PASS'
