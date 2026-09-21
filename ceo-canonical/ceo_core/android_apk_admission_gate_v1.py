from __future__ import annotations
from pathlib import Path
from typing import Any

from .android_apk_inspector_v1 import inspect_apk_v1
from .android_runner_result_import_v1 import import_runner_result_v1


def qualify_apk_admission_v1(bundle_dir: str | Path, *, expected_input_identity_sha256: str,
                             expected_payload_sha256: str) -> dict[str, Any]:
    root = Path(bundle_dir)
    imported = import_runner_result_v1(root, expected_input_identity_sha256=expected_input_identity_sha256,
                                       expected_payload_sha256=expected_payload_sha256)
    if not imported['ok']:
        return {'schema_version': 1, 'ok': False, 'status': 'BLOCKED', 'problems': ['runner_import_failed'] + imported.get('problems', []),
                'runner_import': imported, 'apk_admitted': False, 'production_verified': False}
    apk = root / 'CEO-Android-debug-build1.apk'
    inspection = inspect_apk_v1(apk, expected_sha256=imported['apk_sha256'])
    problems = []
    if not inspection['ok']: problems.extend('inspection:' + p for p in inspection['problems'])
    if inspection.get('signature_verified') is True: problems.append('unexpected_signature_claim')
    ok = not problems
    return {
        'schema_version': 1, 'ok': ok, 'status': 'APK_ADMITTED_FOR_LAB' if ok else 'BLOCKED',
        'problems': sorted(set(problems)), 'apk_sha256': imported['apk_sha256'] if ok else None,
        'apk_size': imported['apk_size'] if ok else None, 'input_identity_sha256': expected_input_identity_sha256,
        'payload_sha256': expected_payload_sha256, 'runner_import': imported, 'inspection': inspection,
        'apk_admitted': ok, 'lab_only': True, 'runtime_verified': False, 'production_verified': False,
        'publication_allowed': False, 'installation_allowed': False,
    }
