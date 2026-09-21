from __future__ import annotations
import hashlib, json
from typing import Any


def qualify_toolchain_license_gate_v1(receipt: dict[str, Any] | None) -> dict[str, Any]:
    row = dict(receipt or {})
    problems: list[str] = []
    if row.get('operator_explicit_acceptance') is not True: problems.append('explicit_operator_acceptance_missing')
    if not str(row.get('accepted_at') or '').strip(): problems.append('accepted_at_missing')
    text_sha = str(row.get('license_set_sha256') or '').lower()
    if len(text_sha) != 64 or any(c not in '0123456789abcdef' for c in text_sha): problems.append('license_set_sha256_invalid')
    if row.get('scope') != 'android_sdk_development_toolchain_only': problems.append('scope_invalid')
    canonical = {k: row.get(k) for k in ('operator_explicit_acceptance','accepted_at','license_set_sha256','scope')}
    return {
        'ok': not problems,
        'status': 'TOOLCHAIN_LICENSE_ACCEPTANCE_RECORDED' if not problems else 'AWAITING_EXPLICIT_OPERATOR_ACCEPTANCE',
        'problems': sorted(set(problems)),
        'receipt_sha256': hashlib.sha256(json.dumps(canonical, sort_keys=True, separators=(',', ':')).encode()).hexdigest(),
        'end_user_setup_required': False,
        'production_verified': False,
    }
