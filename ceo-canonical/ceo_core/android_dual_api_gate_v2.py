from __future__ import annotations
from typing import Any


def qualify_dual_api_runtime_v2(api35: dict[str, Any], api36: dict[str, Any], *, expected_apk_sha256: str,
                                expected_input_identity_sha256: str) -> dict[str, Any]:
    problems=[]
    for row,api in ((api35,35),(api36,36)):
        if row.get('ok') is not True: problems.append(f'api{api}_invalid')
        if row.get('api_level')!=api: problems.append(f'api{api}_level_mismatch')
        if row.get('apk_sha256')!=expected_apk_sha256: problems.append(f'api{api}_apk_mismatch')
        if row.get('input_identity_sha256')!=expected_input_identity_sha256: problems.append(f'api{api}_input_mismatch')
    if api35.get('apk_sha256')!=api36.get('apk_sha256'): problems.append('cross_api_apk_mismatch')
    if api35.get('boot_identity_sha256')==api36.get('boot_identity_sha256'): problems.append('boot_identity_not_independent')
    if api35.get('observation_sha256')==api36.get('observation_sha256'): problems.append('observation_not_independent')
    ok=not problems
    physical=bool(ok and api35.get('source')=='physical_android' and api36.get('source')=='physical_android')
    return {'schema_version':2,'ok':ok,'status':'ANDROID_LAB_RUNTIME_ACCEPTED' if ok else 'BLOCKED','problems':sorted(set(problems)),
            'apk_sha256':expected_apk_sha256 if ok else None,'input_identity_sha256':expected_input_identity_sha256 if ok else None,
            'same_apk_on_api35_api36':ok,'independent_boots':ok,'android_lab_runtime_accepted':ok,
            'physical_android_runtime_accepted':physical,'production_verified':False,'automatic_installation':False}
