import json
from pathlib import Path

from radar_pre160_production_proof_v1 import protected_digest, production_proof_status


def _make_root(tmp_path):
    paths = ('a.txt', 'nested/b.txt')
    (tmp_path / 'nested').mkdir()
    (tmp_path / 'a.txt').write_text('alpha', encoding='utf-8')
    (tmp_path / 'nested/b.txt').write_text('beta', encoding='utf-8')
    return paths


def test_missing_proof_is_not_verified_not_pass(tmp_path):
    paths = _make_root(tmp_path)
    result = production_proof_status(tmp_path, paths=paths)
    assert result['status'] == 'NOT_VERIFIED'
    assert result['verified'] is False
    assert result['reason'] == 'EXTERNAL_PRODUCTION_PROOF_NOT_RECORDED'
    assert result['real_trading'] is False


def test_valid_content_addressed_external_proof_passes(tmp_path):
    paths = _make_root(tmp_path)
    d = protected_digest(tmp_path, paths=paths)['digest']
    proof = {
        'protected_digest': d,
        'audit_conclusion': 'success',
        'tasks_151_200_verified': True,
        'dual_sync_slo_verified': True,
        'stable_windows_version': '1.5.28',
        'real_trading': False,
        'audit_run_id': 123,
        'audited_commit_sha': 'abc',
        'recorded_at': '2026-09-12T00:00:00Z',
    }
    (tmp_path / 'PRE160_PRODUCTION_PROOF.json').write_text(json.dumps(proof), encoding='utf-8')
    result = production_proof_status(tmp_path, paths=paths)
    assert result['status'] == 'PASS'
    assert result['verified'] is True
    assert all(result['checks'].values())
    assert result['proof_file_excluded_from_digest'] is True
    assert result['real_trading'] is False


def test_runtime_change_invalidates_previous_external_proof(tmp_path):
    paths = _make_root(tmp_path)
    d = protected_digest(tmp_path, paths=paths)['digest']
    proof = {
        'protected_digest': d, 'audit_conclusion': 'success',
        'tasks_151_200_verified': True, 'dual_sync_slo_verified': True,
        'stable_windows_version': '1.5.28', 'real_trading': False,
    }
    (tmp_path / 'PRE160_PRODUCTION_PROOF.json').write_text(json.dumps(proof), encoding='utf-8')
    (tmp_path / 'a.txt').write_text('changed-runtime', encoding='utf-8')
    result = production_proof_status(tmp_path, paths=paths)
    assert result['status'] == 'FAILED'
    assert result['verified'] is False
    assert result['checks']['digest_match'] is False
