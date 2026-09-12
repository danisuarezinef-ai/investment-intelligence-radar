"""External production-proof v3 verifier for tasks 301-310.

The runtime can read and verify a proof but cannot create, approve, or persist one.
Every PASS is derived from concrete external observations recorded by CI. Prior task-group
surfaces must be deep-ready; a light fail-closed HTTP response is useful operationally but
is never sufficient for production certification.
"""
from __future__ import annotations

import json
from pathlib import Path

from radar_pre160_production_proof_v1 import protected_digest

REAL_TRADING = False
DEFAULT_PATH = 'PRE160_PRODUCTION_PROOF_V3.json'


def _pass(checks, key):
    row = checks.get(key) if isinstance(checks, dict) else None
    return isinstance(row, dict) and row.get('status') == 'PASS' and bool(row.get('evidence'))


def _deep_group_pass(checks, key):
    row = checks.get(key) if isinstance(checks, dict) else None
    evidence = row.get('evidence') if isinstance(row,dict) and isinstance(row.get('evidence'),dict) else {}
    return bool(row and row.get('status')=='PASS' and evidence.get('http_200') is True and
                evidence.get('source_ready') is True and evidence.get('deep_ready') is True and
                evidence.get('real_trading') is False)


def verify_proof_v3(root='.', path=DEFAULT_PATH):
    root = Path(root)
    digest = protected_digest(root)
    p = root / path
    base = {
        'proof_version': 3,
        'protected_digest': digest.get('digest'),
        'protected_files': digest.get('files'),
        'setup_allowed': False,
        'automatic_release': False,
        'can_trade': False,
        'real_trading': False,
    }
    if digest.get('missing'):
        return {**base, 'status': 'FAILED', 'verified': False, 'reason': 'PROTECTED_FILES_MISSING', 'missing': digest['missing']}
    if not p.exists():
        return {**base, 'status': 'NOT_VERIFIED', 'verified': False, 'reason': 'EXTERNAL_V3_PROOF_NOT_RECORDED', 'checks': {}}
    try:
        proof = json.loads(p.read_text(encoding='utf-8-sig'))
    except Exception as exc:
        return {**base, 'status': 'FAILED', 'verified': False, 'reason': 'INVALID_V3_PROOF', 'error': str(exc)[:300], 'checks': {}}
    checks = proof.get('checks') if isinstance(proof.get('checks'), dict) else {}
    derived = {
        'audit_success': proof.get('audit_conclusion') == 'success',
        'digest_match': proof.get('protected_digest') == digest.get('digest'),
        'exact_sha': bool(proof.get('audited_commit_sha')) and proof.get('audited_commit_sha') == proof.get('railway_deployed_sha'),
        'tasks_151_200': _deep_group_pass(checks, 'tasks_151_200'),
        'tasks_201_270': _deep_group_pass(checks, 'tasks_201_270'),
        'dual_sync': _pass(checks, 'dual_sync'),
        'queue_remote': _pass(checks, 'queue_remote'),
        'tamper_test': _pass(checks, 'tamper_test'),
        'stale_deployment_test': _pass(checks, 'stale_deployment_test'),
        'failed_audit_propagation': _pass(checks, 'failed_audit_propagation'),
        'windows_stable': proof.get('stable_windows_version') == '1.5.28',
        'real_trading_false': proof.get('real_trading') is False,
        'external_run_recorded': bool(proof.get('audit_run_id')),
    }
    verified = all(derived.values())
    return {
        **base,
        'status': 'PASS' if verified else 'FAILED',
        'verified': verified,
        'reason': None if verified else 'ONE_OR_MORE_DERIVED_CHECKS_FAILED',
        'derived_checks': derived,
        'checks': checks,
        'audit_run_id': proof.get('audit_run_id'),
        'audited_commit_sha': proof.get('audited_commit_sha'),
        'railway_deployed_sha': proof.get('railway_deployed_sha'),
        'no_self_certification': True,
        'proof_file_excluded_from_digest': True,
    }


def proof_v3_contract():
    return {
        'derived_not_asserted': True,
        'requires_exact_sha': True,
        'requires_protected_digest': True,
        'requires_dual_sync_evidence': True,
        'requires_prior_task_groups': ['151-200', '201-270'],
        'requires_prior_groups_deep_ready': True,
        'light_surface_cannot_certify': True,
        'requires_tamper_test': True,
        'requires_stale_deployment_test': True,
        'requires_failed_audit_propagation': True,
        'runtime_can_create_proof': False,
        'runtime_can_approve_proof': False,
        'real_trading': False,
    }
