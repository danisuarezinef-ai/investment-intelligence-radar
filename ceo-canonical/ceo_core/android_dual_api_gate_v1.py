from __future__ import annotations
from typing import Any


def qualify_dual_api_runtime_v1(api35: dict[str, Any], api36: dict[str, Any], *, expected_apk_sha256: str,
                                expected_input_identity_sha256: str) -> dict[str, Any]:
    problems: list[str] = []
    if not api35.get('ok') or api35.get('api_level') != 35: problems.append('api35_invalid')
    if not api36.get('ok') or api36.get('api_level') != 36: problems.append('api36_invalid')
    for row, name in ((api35, 'api35'), (api36, 'api36')):
        if row.get('apk_sha256') != expected_apk_sha256: problems.append(name + '_apk_mismatch')
        if row.get('input_identity_sha256') != expected_input_identity_sha256: problems.append(name + '_input_identity_mismatch')
    if api35.get('apk_sha256') != api36.get('apk_sha256'): problems.append('cross_api_apk_mismatch')
    lab_ok = not problems
    physical_phone = bool(api35.get('physical_device') and api36.get('physical_device'))
    return {
        'ok': lab_ok,
        'status': 'ANDROID_LAB_RUNTIME_ACCEPTED' if lab_ok else 'BLOCKED',
        'problems': sorted(set(problems)),
        'same_apk_on_api35_api36': lab_ok,
        'android_lab_runtime_accepted': lab_ok,
        'physical_android_runtime_accepted': bool(lab_ok and physical_phone),
        'production_verified': False,
        'automatic_installation': False,
    }
