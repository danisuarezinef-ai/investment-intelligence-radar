"""Deterministic recovery and reproducibility authority for pre-1.6.

The manifest is descriptive and fail-closed. It never reconstructs missing evidence,
never backfills trades, and never grants release/trading authority.
"""
from __future__ import annotations

import hashlib
import json

REAL_TRADING = False
_VOLATILE_KEYS = {
    'observed_at', 'cache_seconds', 'edge_ms', 'last_latency_ms', 'last_success_epoch',
    'last_error_epoch', 'circuit_remaining_seconds', 'generated_at', 'updated_at',
}


def _stable(value):
    if isinstance(value, dict):
        return {str(k): _stable(v) for k, v in sorted(value.items(), key=lambda kv: str(kv[0])) if str(k) not in _VOLATILE_KEYS}
    if isinstance(value, (list, tuple)):
        return [_stable(x) for x in value]
    if isinstance(value, float):
        return float(format(value, '.15g'))
    return value


def canonical_json(value):
    return json.dumps(_stable(value), sort_keys=True, separators=(',', ':'), ensure_ascii=False, default=str)


def digest(value):
    return hashlib.sha256(canonical_json(value).encode('utf-8')).hexdigest()


def build_recovery_manifest(*, evidence, hardening, health, task_matrix, version='1.5.28'):
    protected = {
        'evidence': _stable(evidence or {}),
        'hardening': _stable(hardening or {}),
        'persistence_health': _stable(health or {}),
        'task_states': {str(k): (v or {}).get('state') for k, v in sorted((task_matrix or {}).get('tasks', {}).items())},
        'stable_windows_version': str(version),
        'checkpoint_schema_support': [1, 2],
        'real_trading': False,
    }
    components = {name: digest(value) for name, value in protected.items()}
    root = digest({'components': components, 'schema': 2})
    return {
        'status': 'RECOVERY_MANIFEST_V2',
        'schema_version': 2,
        'protected_components': components,
        'root_digest': root,
        'digest_algorithm': 'SHA-256',
        'checkpoint_schema_support': [1, 2],
        'reconstruction_allowed': False,
        'backfill_allowed': False,
        'setup_allowed': False,
        'can_trade': False,
        'real_trading': False,
    }


def compare_recovery_manifests(before, after):
    before = before if isinstance(before, dict) else {}
    after = after if isinstance(after, dict) else {}
    a = before.get('protected_components') if isinstance(before.get('protected_components'), dict) else {}
    b = after.get('protected_components') if isinstance(after.get('protected_components'), dict) else {}
    keys = sorted(set(a) | set(b))
    missing_before = [k for k in keys if k not in a]
    missing_after = [k for k in keys if k not in b]
    changed = [k for k in keys if k in a and k in b and a[k] != b[k]]
    same_root = bool(before.get('root_digest')) and before.get('root_digest') == after.get('root_digest')
    ok = not missing_before and not missing_after and not changed and same_root
    return {
        'status': 'PASS' if ok else 'FAILED',
        'exact_restore': bool(ok),
        'changed_components': changed,
        'missing_before': missing_before,
        'missing_after': missing_after,
        'root_digest_match': same_root,
        'reconstruction_used': False,
        'backfill_used': False,
        'can_trade': False,
        'real_trading': False,
    }
