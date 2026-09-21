from __future__ import annotations

import hashlib
import json
from typing import Any


def _sha(value: Any) -> bool:
    text = str(value or '').strip().lower()
    return len(text) == 64 and all(c in '0123456789abcdef' for c in text)


def _canon(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')


def build_debug_build_receipt_v2(*, input_identity_sha256: str, source_payload_sha256: str,
                                 apk_sha256: str, apk_size: int, build_ordinal: int,
                                 jdk: str, gradle: str, compile_sdk: int,
                                 build_tools: str, builder_kind: str = 'ci_or_dev') -> dict[str, Any]:
    problems: list[str] = []
    for key, value in {
        'input_identity_sha256': input_identity_sha256,
        'source_payload_sha256': source_payload_sha256,
        'apk_sha256': apk_sha256,
    }.items():
        if not _sha(value): problems.append(key + '_invalid')
    if int(apk_size) <= 0: problems.append('apk_size_invalid')
    if int(build_ordinal) not in (1, 2): problems.append('build_ordinal_invalid')
    if str(jdk) != '17': problems.append('jdk_mismatch')
    if str(gradle) != '9.4.1': problems.append('gradle_mismatch')
    if int(compile_sdk) != 37: problems.append('compile_sdk_mismatch')
    if str(build_tools) != '37.0.0': problems.append('build_tools_mismatch')
    if builder_kind not in {'ci_or_dev', 'ephemeral_lab'}: problems.append('builder_kind_invalid')
    row = {
        'schema_version': 2,
        'input_identity_sha256': str(input_identity_sha256).lower(),
        'source_payload_sha256': str(source_payload_sha256).lower(),
        'apk_sha256': str(apk_sha256).lower(),
        'apk_size': int(apk_size),
        'build_ordinal': int(build_ordinal),
        'toolchain': {'jdk': str(jdk), 'gradle': str(gradle), 'compile_sdk': int(compile_sdk), 'build_tools': str(build_tools)},
        'builder_kind': builder_kind,
        'debug_only': True,
        'release_signed': False,
        'production_verified': False,
    }
    row['receipt_sha256'] = hashlib.sha256(_canon(row)).hexdigest()
    return {'ok': not problems, 'status': 'DEBUG_BUILD_RECEIPT_VALID' if not problems else 'BLOCKED', 'problems': sorted(set(problems)), **row}


def compare_build_receipts_v2(first: dict[str, Any], second: dict[str, Any]) -> dict[str, Any]:
    problems: list[str] = []
    if not first.get('ok'): problems.append('first_invalid')
    if not second.get('ok'): problems.append('second_invalid')
    if first.get('build_ordinal') != 1: problems.append('first_ordinal_invalid')
    if second.get('build_ordinal') != 2: problems.append('second_ordinal_invalid')
    for key in ('input_identity_sha256', 'source_payload_sha256', 'apk_sha256', 'apk_size'):
        if first.get(key) != second.get(key): problems.append(key + '_mismatch')
    if first.get('toolchain') != second.get('toolchain'): problems.append('toolchain_mismatch')
    return {
        'ok': not problems,
        'status': 'DEBUG_APK_REPRODUCIBLE' if not problems else 'BLOCKED',
        'problems': sorted(set(problems)),
        'apk_sha256': first.get('apk_sha256') if not problems else None,
        'input_identity_sha256': first.get('input_identity_sha256') if not problems else None,
        'reproducibility_verified': not problems,
        'automatic_installation': False,
        'production_verified': False,
    }
