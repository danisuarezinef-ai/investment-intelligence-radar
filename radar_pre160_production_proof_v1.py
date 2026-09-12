"""Content-addressed proof verifier for the external tasks 151-200 production audit.

The proof is deliberately a separate reviewed artifact created only after an external
CI run succeeds. Its protected digest excludes only the proof JSON itself, so recording
the externally observed proof does not invalidate the already-audited runtime code.
This module never creates or self-approves proof.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

REAL_TRADING = False
DEFAULT_PROOF_PATH = 'PRE160_PRODUCTION_PROOF.json'

# These files collectively define the deployed authority/readiness/provenance chain.
# The proof verifier itself is protected; only PRE160_PRODUCTION_PROOF.json is excluded.
PROTECTED_PATHS = (
    'version.json',
    'start.sh',
    'cloud_service_v3.py',
    'cloud_service_v4.py',
    'cloud_service_v5.py',
    'cloud_service_v6.py',
    'radar_supabase_sync.py',
    'radar_learning_sync.py',
    'radar_forward_outcome_sync_v1.py',
    'radar_closed_loop_runtime_v1.py',
    'radar_champion_challenger_v1.py',
    'radar_learning_engine_v3.py',
    'radar_validation_runtime_v3.py',
    'radar_pre160_cloud_v3.py',
    'radar_pre160_cloud_v4.py',
    'radar_pre160_runtime_v3.py',
    'radar_pre160_runtime_v4.py',
    'radar_pre160_runtime_v4_linkage.py',
    'radar_pre160_runtime_v5.py',
    'radar_pre160_controls_v6.py',
    'radar_pre160_recovery_v2.py',
    'radar_pre160_release_authority_v2.py',
    'radar_pre160_production_proof_v1.py',
    'radar_pre160_persistence_v1.py',
    'radar_pre160_evidence_persistence_v1.py',
    'radar_pre160_hardening_persistence_v1.py',
    'radar_paper_engine_persistence_v1.py',
    'radar_agents.py',
    'radar_champion_portfolio.py',
    'radar_causal_scoring_v2.py',
    'radar_promotion_governance_v2.py',
    'supabase/functions/radar-sync/index.ts',
    'supabase/functions/radar-learning-sync/index.ts',
    'supabase/functions/radar-paper-engine-checkpoint/index.ts',
    'supabase/functions/radar-pre160-evidence/index.ts',
    'supabase/functions/radar-pre160-hardening/index.ts',
    '.github/workflows/pre160-hardening-production-audit.yml',
)


def protected_digest(root='.', paths=PROTECTED_PATHS):
    root = Path(root)
    h = hashlib.sha256()
    missing = []
    ordered = tuple(sorted(str(x) for x in paths))
    for rel in ordered:
        path = root / rel
        if not path.exists() or not path.is_file():
            missing.append(rel)
            continue
        raw = path.read_bytes()
        h.update(rel.encode('utf-8')); h.update(b'\0')
        h.update(hashlib.sha256(raw).digest()); h.update(b'\0')
    return {
        'digest': h.hexdigest() if not missing else None,
        'missing': missing,
        'files': len(ordered),
        'algorithm': 'SHA-256',
        'proof_json_excluded': DEFAULT_PROOF_PATH not in ordered,
    }


def production_proof_status(root='.', proof_path=DEFAULT_PROOF_PATH, paths=PROTECTED_PATHS):
    current = protected_digest(root, paths)
    path = Path(root) / proof_path
    if current['missing']:
        return {
            'status': 'FAILED', 'verified': False, 'reason': 'PROTECTED_FILES_MISSING',
            'missing': current['missing'], 'protected_files': current['files'], 'real_trading': False,
        }
    if not path.exists():
        return {
            'status': 'NOT_VERIFIED', 'verified': False, 'reason': 'EXTERNAL_PRODUCTION_PROOF_NOT_RECORDED',
            'protected_digest': current['digest'], 'protected_files': current['files'],
            'digest_algorithm': current['algorithm'], 'proof_json_excluded': current['proof_json_excluded'],
            'setup_allowed': False, 'can_trade': False, 'real_trading': False,
        }
    try:
        proof = json.loads(path.read_text(encoding='utf-8-sig'))
    except Exception as exc:
        return {'status': 'FAILED', 'verified': False, 'reason': 'INVALID_PROOF_JSON', 'error': str(exc)[:300], 'real_trading': False}
    checks = {
        'digest_match': proof.get('protected_digest') == current['digest'],
        'ci_success': proof.get('audit_conclusion') == 'success',
        'tasks_verified': proof.get('tasks_151_200_verified') is True,
        'dual_sync_slo_verified': proof.get('dual_sync_slo_verified') is True,
        'windows_stable': proof.get('stable_windows_version') == '1.5.28',
        'real_trading_false': proof.get('real_trading') is False,
        'audit_run_recorded': proof.get('audit_run_id') not in (None, ''),
        'audited_commit_recorded': bool(str(proof.get('audited_commit_sha') or '').strip()),
    }
    verified = all(checks.values())
    return {
        'status': 'PASS' if verified else 'FAILED',
        'verified': verified,
        'protected_digest': current['digest'],
        'protected_files': current['files'],
        'digest_algorithm': current['algorithm'],
        'checks': checks,
        'audit_run_id': proof.get('audit_run_id'),
        'audited_commit_sha': proof.get('audited_commit_sha'),
        'recorded_at': proof.get('recorded_at'),
        'proof_is_content_addressed': True,
        'proof_file_excluded_from_digest': True,
        'self_verifier_is_protected': 'radar_pre160_production_proof_v1.py' in tuple(paths),
        'setup_allowed': False,
        'can_trade': False,
        'real_trading': False,
    }
