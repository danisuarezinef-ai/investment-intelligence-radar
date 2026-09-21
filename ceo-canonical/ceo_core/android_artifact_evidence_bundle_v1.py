from __future__ import annotations
import hashlib, json
from typing import Any


def _canon(v: Any) -> bytes: return json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()

def build_artifact_evidence_bundle_v1(*,admission:dict[str,Any],dual_api:dict[str,Any])->dict[str,Any]:
    problems=[]
    if admission.get('ok') is not True or admission.get('apk_admitted') is not True: problems.append('apk_not_admitted')
    if dual_api.get('ok') is not True or dual_api.get('android_lab_runtime_accepted') is not True: problems.append('runtime_not_accepted')
    if admission.get('apk_sha256')!=dual_api.get('apk_sha256'): problems.append('apk_identity_mismatch')
    if admission.get('input_identity_sha256')!=dual_api.get('input_identity_sha256'): problems.append('input_identity_mismatch')
    row={'schema_version':1,'apk_sha256':admission.get('apk_sha256'),'input_identity_sha256':admission.get('input_identity_sha256'),
         'payload_sha256':admission.get('payload_sha256'),'build_bytes_verified_twice':bool(admission.get('runner_import',{}).get('bytes_verified_twice')),
         'apk_admitted':admission.get('apk_admitted') is True,'android_lab_runtime_accepted':dual_api.get('android_lab_runtime_accepted') is True,
         'physical_android_runtime_accepted':dual_api.get('physical_android_runtime_accepted') is True,'problems':sorted(set(problems)),
         'production_verified':False,'publication_allowed':False,'installation_allowed':False}
    row['ok']=not row['problems']; row['status']='ANDROID_ARTIFACT_EVIDENCE_COMPLETE' if row['ok'] else 'BLOCKED'
    row['bundle_sha256']=hashlib.sha256(_canon(row)).hexdigest()
    return row
