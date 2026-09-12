"""Manual-review-only 1.6 release authority.

This authority can say whether an evidence package is ready for human review. It
cannot build, sign, publish, install, promote/demote strategies or enable trading.
"""
from __future__ import annotations

import hashlib
import json

REAL_TRADING = False
BLOCKING_STATES = {'FAILED', 'NOT_VERIFIED', 'PENDING_TIME', 'PENDING_SAMPLE'}


def _digest(value):
    raw = json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, default=str)
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


def build_release_authority(task_matrix, recovery_manifest, *, stable_version='1.5.28', candidate_version='1.6.0'):
    matrix = task_matrix if isinstance(task_matrix, dict) else {}
    tasks = matrix.get('tasks') if isinstance(matrix.get('tasks'), dict) else {}
    critical = []
    for task_id, row in sorted(tasks.items(), key=lambda kv: int(kv[0])):
        row = row if isinstance(row, dict) else {}
        if row.get('critical') and row.get('state') in BLOCKING_STATES:
            critical.append({'task': int(task_id), 'state': row.get('state'), 'detail': row.get('detail')})
    recovery_ok = isinstance(recovery_manifest, dict) and len(str(recovery_manifest.get('root_digest') or '')) == 64
    if not recovery_ok:
        critical.append({'task': 191, 'state': 'NOT_VERIFIED', 'detail': 'recovery manifest missing or invalid'})
    ready = not critical and len(tasks) == 50
    bundle = {
        'stable_version': str(stable_version),
        'candidate_version': str(candidate_version),
        'task_states': {str(k): (v or {}).get('state') for k, v in sorted(tasks.items(), key=lambda kv: int(kv[0]))},
        'recovery_root_digest': (recovery_manifest or {}).get('root_digest'),
        'manual_review_only': True,
    }
    return {
        'status': 'READY_FOR_MANUAL_1_6_REVIEW' if ready else 'BLOCKED_PRE160',
        'stable_windows_version': str(stable_version),
        'candidate_version': str(candidate_version),
        'task_count': len(tasks),
        'critical_blockers': critical,
        'evidence_bundle_digest': _digest(bundle),
        'manual_review_only': True,
        'release_review_ready': bool(ready),
        'setup_allowed': False,
        'setup_built': False,
        'automatic_release': False,
        'automatic_promotion': False,
        'automatic_demotion': False,
        'live_review_allowed': False,
        'live_execution_allowed': False,
        'can_trade': False,
        'real_trading': False,
    }
