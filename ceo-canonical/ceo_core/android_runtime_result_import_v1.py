from __future__ import annotations
import hashlib, json
from pathlib import Path
from typing import Any
from .android_runtime_evidence_v3 import REQUIRED_PROBES


def _canon(v: Any) -> bytes:
    return json.dumps(v, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()


def validate_runtime_observation_import_v1(row: dict[str, Any], *, expected_api_level: int,
                                           expected_apk_sha256: str, expected_input_identity_sha256: str) -> dict[str, Any]:
    problems=[]
    if row.get('api_level')!=expected_api_level: problems.append('api_level_mismatch')
    if row.get('apk_sha256')!=expected_apk_sha256: problems.append('apk_sha256_mismatch')
    if row.get('input_identity_sha256')!=expected_input_identity_sha256: problems.append('input_identity_mismatch')
    if row.get('source') not in {'android_emulator','physical_android'}: problems.append('source_invalid')
    if row.get('runtime_pass') is not True or row.get('ok') is not True: problems.append('runtime_not_pass')
    probes=row.get('probes') or {}
    if not all(probes.get(k) is True for k in REQUIRED_PROBES): problems.append('required_probe_missing_or_failed')
    for k in ('device_identity_sha256','boot_identity_sha256'):
        v=str(row.get(k) or '')
        if len(v)!=64 or any(c not in '0123456789abcdef' for c in v.lower()): problems.append(k+'_invalid')
    got=row.get('observation_sha256'); base=dict(row); base.pop('ok',None); base.pop('status',None); base.pop('problems',None); base.pop('observation_sha256',None)
    expected=hashlib.sha256(_canon(base)).hexdigest()
    if got!=expected: problems.append('observation_digest_mismatch')
    if row.get('production_verified') is not False: problems.append('production_overclaim')
    ok=not problems
    return {'schema_version':1,'ok':ok,'status':'RUNTIME_EVIDENCE_IMPORTED' if ok else 'BLOCKED','problems':sorted(set(problems)),
            'api_level':expected_api_level,'apk_sha256':expected_apk_sha256 if ok else None,
            'input_identity_sha256':expected_input_identity_sha256 if ok else None,'source':row.get('source'),
            'device_identity_sha256':row.get('device_identity_sha256'),'boot_identity_sha256':row.get('boot_identity_sha256'),
            'observation_sha256':got,'production_verified':False}


def import_runtime_result_file_v1(path: str | Path, **kwargs: Any) -> dict[str, Any]:
    p=Path(path)
    if not p.is_file(): return {'schema_version':1,'ok':False,'status':'INCOMPLETE_EVIDENCE','problems':['runtime_file_missing'],'production_verified':False}
    try: row=json.loads(p.read_text(encoding='utf-8'))
    except Exception: return {'schema_version':1,'ok':False,'status':'BLOCKED','problems':['runtime_json_invalid'],'production_verified':False}
    return validate_runtime_observation_import_v1(row,**kwargs)
