from __future__ import annotations
import hashlib, json, re
from typing import Any

FORBIDDEN=('release_sign','publish','production_install','payment','real_trading')

def build_ci_capsule_manifest_v1(*,input_identity_sha256:str,payload_sha256:str,consent_sha256:str,kit_sha256:str)->dict[str,Any]:
    row={'schema_version':1,'input_identity_sha256':input_identity_sha256,'payload_sha256':payload_sha256,
         'operator_consent_sha256':consent_sha256,'build_kit_sha256':kit_sha256,'runner_os':'linux',
         'required_jdk':'17','required_gradle':'9.4.1','compile_sdk':37,'build_tools':'37.0.0',
         'clean_build_count':2,'forbidden_capabilities':list(FORBIDDEN),'artifact_output':'debug_apk_only'}
    row['manifest_sha256']=hashlib.sha256(json.dumps(row,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    return row

def validate_ci_capsule_manifest_v1(row:dict[str,Any])->dict[str,Any]:
    p=[]
    for k in ('input_identity_sha256','payload_sha256','operator_consent_sha256','build_kit_sha256','manifest_sha256'):
        if not re.fullmatch(r'[0-9a-f]{64}',str(row.get(k) or '')): p.append(k)
    base=dict(row); got=base.pop('manifest_sha256',None)
    exp=hashlib.sha256(json.dumps(base,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    if got!=exp: p.append('manifest_digest')
    if row.get('clean_build_count')!=2 or row.get('artifact_output')!='debug_apk_only': p.append('build_policy')
    if set(FORBIDDEN)-set(row.get('forbidden_capabilities') or []): p.append('authority_boundary')
    return {'ok':not p,'problems':p}
