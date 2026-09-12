import cloud_service_v4 as service
import radar_pre160_cloud_v3 as cloud3
import radar_pre160_cloud_v4 as cloud4


def _reset_service_caches():
    service._PRE160_V3_CACHE.update({'at': 0.0, 'evidence': None, 'audit': None})
    service._PRE160_V3_AUTHORITY_CACHE.update({'at': 0.0, 'authority': None})
    service._PRE160_V4_CACHE.update({'at': 0.0, 'hardening': None, 'audit': None, 'audit_131_150': None})
    service._PRE160_V4_AUTHORITY_CACHE.update({'at': 0.0, 'authority': None})


def test_cold_evidence_request_builds_expensive_snapshot_once(monkeypatch):
    _reset_service_caches()
    calls = {'snapshot': 0, 'audit': 0, 'authority': 0}
    snapshot = {'status': 'PRE160_EVIDENCE_V3', 'snapshot_hash': 'e' * 64, 'real_trading': False}

    def build():
        calls['snapshot'] += 1
        return dict(snapshot)

    def audit(value):
        calls['audit'] += 1
        assert value.get('snapshot_hash') == 'e' * 64
        return {'status': 'PRE160_TASKS_91_110', 'tasks': {}, 'real_trading': False}

    def authority(_days):
        calls['authority'] += 1
        raise AssertionError('evidence endpoint must not synchronously fetch authority report')

    monkeypatch.setattr(service, 'evidence_snapshot_v3', build)
    monkeypatch.setattr(service, 'tasks_91_110_audit', audit)
    monkeypatch.setattr(service, 'evidence_authority_report', authority)

    first = service.pre160_evidence_cached(force=True)
    second = service.pre160_evidence_cached()
    a = service.tasks_91_110_cached()

    assert first['snapshot_hash'] == second['snapshot_hash'] == 'e' * 64
    assert a['status'] == 'PRE160_TASKS_91_110'
    assert calls == {'snapshot': 1, 'audit': 1, 'authority': 0}
    assert first['cache_compute_ms'] >= 0
    assert first['real_trading'] is False


def test_evidence_authority_cache_is_independent(monkeypatch):
    _reset_service_caches()
    calls = {'authority': 0}
    monkeypatch.setattr(service, 'evidence_snapshot_v3', lambda: (_ for _ in ()).throw(AssertionError('snapshot must not run')))

    def authority(days):
        calls['authority'] += 1
        assert days == 90
        return {'status': 'PRE160_EVIDENCE_AUTHORITY', 'chain_records': 4, 'real_trading': False}

    monkeypatch.setattr(service, 'evidence_authority_report', authority)
    first = service.pre160_authority_cached(force=True)
    second = service.pre160_authority_cached()
    assert first['status'] == second['status'] == 'PRE160_EVIDENCE_AUTHORITY'
    assert calls['authority'] == 1
    assert first['cache_compute_ms'] >= 0


def test_cold_hardening_request_builds_expensive_snapshot_once(monkeypatch):
    _reset_service_caches()
    calls = {'snapshot': 0, 'a111': 0, 'a131': 0, 'authority': 0}
    snapshot = {'status': 'PRE160_EVIDENCE_V5', 'snapshot_hash': 'x' * 64, 'real_trading': False}

    def build():
        calls['snapshot'] += 1
        return dict(snapshot)

    def a111(value):
        calls['a111'] += 1
        assert value.get('snapshot_hash') == 'x' * 64
        return {'status': 'PRE160_TASKS_111_130', 'tasks': {}, 'real_trading': False}

    def a131(value):
        calls['a131'] += 1
        assert value.get('snapshot_hash') == 'x' * 64
        return {'status': 'PRE160_TASKS_131_150', 'tasks': {}, 'real_trading': False}

    def authority(_limit):
        calls['authority'] += 1
        raise AssertionError('hardening endpoint must not synchronously fetch authority report')

    monkeypatch.setattr(service, 'hardening_snapshot_v4', build)
    monkeypatch.setattr(service, 'tasks_111_130_audit', a111)
    monkeypatch.setattr(service, 'tasks_131_150_audit', a131)
    monkeypatch.setattr(service, 'hardening_authority_report', authority)

    first = service.pre160_hardening_cached(force=True)
    second = service.pre160_hardening_cached()
    a = service.tasks_111_130_cached()
    b = service.tasks_131_150_cached()

    assert first['snapshot_hash'] == second['snapshot_hash'] == 'x' * 64
    assert a['status'] == 'PRE160_TASKS_111_130'
    assert b['status'] == 'PRE160_TASKS_131_150'
    assert calls == {'snapshot': 1, 'a111': 1, 'a131': 1, 'authority': 0}
    assert first['cache_compute_ms'] >= 0
    assert first['real_trading'] is False


def test_hardening_authority_cache_is_independent_from_expensive_snapshot(monkeypatch):
    _reset_service_caches()
    calls = {'authority': 0}
    monkeypatch.setattr(service, 'hardening_snapshot_v4', lambda: (_ for _ in ()).throw(AssertionError('snapshot must not run')))

    def authority(limit):
        calls['authority'] += 1
        assert limit == 500
        return {'status': 'PRE160_HARDENING_AUTHORITY', 'checkpoint_records': 7, 'real_trading': False}

    monkeypatch.setattr(service, 'hardening_authority_report', authority)
    first = service.pre160_hardening_authority_cached(force=True)
    second = service.pre160_hardening_authority_cached()
    assert first['status'] == second['status'] == 'PRE160_HARDENING_AUTHORITY'
    assert calls['authority'] == 1
    assert first['cache_compute_ms'] >= 0
    assert first['real_trading'] is False


def test_audit_projections_accept_existing_snapshots_without_rebuilding(monkeypatch):
    monkeypatch.setattr(cloud3, 'evidence_snapshot_v3', lambda: (_ for _ in ()).throw(AssertionError('must reuse supplied evidence')))
    evidence = {
        'snapshot_hash': 'y' * 64,
        'sample_gates': {}, 'readiness_1_6': {}, 'contexts_to_freeze': [],
        'authority_before_persist': {'chain_integrity': 'VERIFIED'},
    }
    a91 = cloud3.tasks_91_110_audit(evidence)
    assert a91['snapshot_hash'] == 'y' * 64

    monkeypatch.setattr(cloud4, 'hardening_snapshot_v4', lambda: (_ for _ in ()).throw(AssertionError('must reuse supplied hardening')))
    hardening = {
        'snapshot_hash': 'z' * 64,
        'checkpoint_continuity': {'status': 'VERIFIED', 'checkpoints': 8, 'gaps': []},
        'decision_envelope_provenance': {'transactional_exact': 1, 'ledger_fallback': 0, 'strategy_versions_missing': 0},
        'decision_trace': {'status': 'COMPLETE', 'blockers': []},
        'envelope_source': {'remote_frozen': 1, 'local_candidates': 1},
        'regime_coverage': {},
    }
    a111 = cloud4.tasks_111_130_audit(hardening)
    a131 = cloud4.tasks_131_150_audit(hardening)
    assert a111['snapshot_hash'] == 'z' * 64
    assert a111['tasks']['130'] == 'VERIFIED_REDEPLOY_CHAIN'
    assert a131['transactional_exact'] == 1
    assert a131['ledger_fallback'] == 0
    assert a131['real_trading'] is False


def test_cache_layer_has_stampede_locks_and_never_changes_trading_boundary():
    text = __import__('pathlib').Path('cloud_service_v4.py').read_text(encoding='utf-8')
    assert '_PRE160_V3_LOCK=threading.Lock()' in text
    assert '_PRE160_V3_AUTHORITY_LOCK=threading.Lock()' in text
    assert '_PRE160_V4_LOCK=threading.Lock()' in text
    assert '_PRE160_V4_AUTHORITY_LOCK=threading.Lock()' in text
    assert 'REAL_TRADING=False' in text
