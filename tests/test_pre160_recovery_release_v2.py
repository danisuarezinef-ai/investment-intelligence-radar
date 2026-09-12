from copy import deepcopy

from radar_pre160_recovery_v2 import build_recovery_manifest, compare_recovery_manifests
from radar_pre160_release_authority_v2 import build_release_authority


def _matrix(state='PASS'):
    tasks = {
        str(i): {'task': i, 'state': state, 'critical': i in {151, 160, 170, 180, 191, 198, 199, 200}, 'detail': 'x'}
        for i in range(151, 201)
    }
    return {'status': 'PRE160_TASKS_151_200', 'tasks': tasks, 'real_trading': False}


def test_recovery_manifest_is_deterministic_and_ignores_volatile_timing():
    base = dict(
        evidence={'status': 'OK', 'observed_at': 'one', 'payload': {'x': 1}},
        hardening={'status': 'OK', 'cache_seconds': 60, 'payload': {'y': 2}},
        health={'status': 'HEALTHY', 'last_latency_ms': 10.0},
        task_matrix=_matrix(),
        version='1.5.28',
    )
    a = build_recovery_manifest(**base)
    changed = deepcopy(base)
    changed['evidence']['observed_at'] = 'two'
    changed['health']['last_latency_ms'] = 999.0
    b = build_recovery_manifest(**changed)
    assert a['root_digest'] == b['root_digest']
    assert len(a['root_digest']) == 64
    assert a['checkpoint_schema_support'] == [1, 2]
    assert a['backfill_allowed'] is False
    assert a['reconstruction_allowed'] is False
    assert a['real_trading'] is False


def test_restore_comparator_detects_protected_change_fail_closed():
    a = build_recovery_manifest(
        evidence={'x': 1}, hardening={'y': 2}, health={'status': 'HEALTHY'}, task_matrix=_matrix(), version='1.5.28'
    )
    b = build_recovery_manifest(
        evidence={'x': 9}, hardening={'y': 2}, health={'status': 'HEALTHY'}, task_matrix=_matrix(), version='1.5.28'
    )
    result = compare_recovery_manifests(a, b)
    assert result['status'] == 'FAILED'
    assert result['exact_restore'] is False
    assert 'evidence' in result['changed_components']
    assert result['backfill_used'] is False
    assert result['reconstruction_used'] is False
    assert result['real_trading'] is False


def test_exact_restore_comparator_passes_identical_manifest():
    a = build_recovery_manifest(
        evidence={'x': 1}, hardening={'y': 2}, health={'status': 'HEALTHY'}, task_matrix=_matrix(), version='1.5.28'
    )
    result = compare_recovery_manifests(a, deepcopy(a))
    assert result['status'] == 'PASS'
    assert result['exact_restore'] is True
    assert result['changed_components'] == []


def test_release_authority_is_manual_only_even_when_every_task_passes():
    matrix = _matrix('PASS')
    manifest = build_recovery_manifest(
        evidence={'x': 1}, hardening={'y': 2}, health={'status': 'HEALTHY'}, task_matrix=matrix, version='1.5.28'
    )
    release = build_release_authority(matrix, manifest, stable_version='1.5.28', candidate_version='1.6.0')
    assert release['status'] == 'READY_FOR_MANUAL_1_6_REVIEW'
    assert release['release_review_ready'] is True
    assert release['manual_review_only'] is True
    assert release['setup_allowed'] is False
    assert release['setup_built'] is False
    assert release['automatic_release'] is False
    assert release['automatic_promotion'] is False
    assert release['automatic_demotion'] is False
    assert release['live_execution_allowed'] is False
    assert release['real_trading'] is False


def test_pending_time_or_sample_blocks_manual_review():
    matrix = _matrix('PASS')
    matrix['tasks']['173']['critical'] = True
    matrix['tasks']['173']['state'] = 'PENDING_TIME'
    matrix['tasks']['180']['critical'] = True
    matrix['tasks']['180']['state'] = 'PENDING_SAMPLE'
    manifest = build_recovery_manifest(
        evidence={'x': 1}, hardening={'y': 2}, health={'status': 'HEALTHY'}, task_matrix=matrix, version='1.5.28'
    )
    release = build_release_authority(matrix, manifest)
    assert release['status'] == 'BLOCKED_PRE160'
    assert release['release_review_ready'] is False
    states = {x['state'] for x in release['critical_blockers']}
    assert 'PENDING_TIME' in states
    assert 'PENDING_SAMPLE' in states
    assert release['setup_allowed'] is False
