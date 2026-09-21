from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .android_build_receipt_v3 import validate_receipt_v3
from .android_reproducibility_gate_v2 import qualify_reproducibility_v2


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def import_runner_result_v1(bundle_dir: str | Path, *, expected_input_identity_sha256: str,
                            expected_payload_sha256: str) -> dict[str, Any]:
    root = Path(bundle_dir)
    problems: list[str] = []
    needed = {
        'result': root / 'DEV162_171_RUNNER_RESULT.json',
        'receipt1': root / 'BUILD_RECEIPT_1.json',
        'receipt2': root / 'BUILD_RECEIPT_2.json',
        'repro': root / 'REPRODUCIBILITY_RECEIPT.json',
        'apk1': root / 'CEO-Android-debug-build1.apk',
        'apk2': root / 'CEO-Android-debug-build2.apk',
    }
    for name, path in needed.items():
        if not path.is_file():
            problems.append(name + '_missing')
    if problems:
        return {'schema_version': 1, 'ok': False, 'status': 'INCOMPLETE_EVIDENCE', 'problems': sorted(problems),
                'apk_built': False, 'apk_reproducible': False, 'production_verified': False}

    try:
        result = json.loads(needed['result'].read_text(encoding='utf-8'))
        r1 = json.loads(needed['receipt1'].read_text(encoding='utf-8'))
        r2 = json.loads(needed['receipt2'].read_text(encoding='utf-8'))
        repro = json.loads(needed['repro'].read_text(encoding='utf-8'))
    except Exception as exc:
        return {'schema_version': 1, 'ok': False, 'status': 'BLOCKED', 'problems': ['json_invalid:' + type(exc).__name__],
                'apk_built': False, 'apk_reproducible': False, 'production_verified': False}

    v1, v2 = validate_receipt_v3(r1), validate_receipt_v3(r2)
    if not v1['ok']: problems.append('receipt1_invalid')
    if not v2['ok']: problems.append('receipt2_invalid')
    rep = qualify_reproducibility_v2(r1, r2)
    if not rep['ok']: problems.append('receipt_pair_not_reproducible')

    a1 = _sha256(needed['apk1']); a2 = _sha256(needed['apk2'])
    s1 = needed['apk1'].stat().st_size; s2 = needed['apk2'].stat().st_size
    if a1 != a2: problems.append('apk_bytes_sha256_mismatch')
    if s1 != s2: problems.append('apk_size_mismatch')
    for idx, (receipt, sha, size) in enumerate(((r1, a1, s1), (r2, a2, s2)), start=1):
        if receipt.get('apk_sha256') != sha: problems.append(f'receipt{idx}_apk_sha_mismatch')
        if int(receipt.get('apk_size') or -1) != size: problems.append(f'receipt{idx}_apk_size_mismatch')
        if receipt.get('input_identity_sha256') != expected_input_identity_sha256: problems.append(f'receipt{idx}_input_identity_mismatch')
        if receipt.get('payload_sha256') != expected_payload_sha256: problems.append(f'receipt{idx}_payload_mismatch')

    if result.get('apk_sha256') != a1: problems.append('runner_result_apk_sha_mismatch')
    if int(result.get('apk_size') or -1) != s1: problems.append('runner_result_apk_size_mismatch')
    if result.get('same_apk_twice') is not True: problems.append('runner_result_same_apk_twice_false')
    if result.get('production_verified') is not False: problems.append('runner_result_overclaims_production')
    if result.get('publication_authorized') is not False: problems.append('runner_result_overclaims_publication')
    if result.get('installation_authorized') is not False: problems.append('runner_result_overclaims_installation')

    repro_apk = repro.get('apk_sha256') or repro.get('artifact_sha256')
    if repro_apk and repro_apk != a1: problems.append('repro_receipt_apk_sha_mismatch')
    if repro.get('ok') is False or repro.get('reproducible') is False: problems.append('repro_receipt_negative')

    ok = not problems
    return {
        'schema_version': 1, 'ok': ok, 'status': 'RUNNER_ARTIFACT_IMPORTED' if ok else 'BLOCKED',
        'problems': sorted(set(problems)), 'apk_sha256': a1 if ok else None, 'apk_size': s1 if ok else None,
        'input_identity_sha256': expected_input_identity_sha256, 'payload_sha256': expected_payload_sha256,
        'apk_built': ok, 'apk_reproducible': ok, 'bytes_verified_twice': ok,
        'production_verified': False, 'publication_allowed': False, 'installation_allowed': False,
    }
