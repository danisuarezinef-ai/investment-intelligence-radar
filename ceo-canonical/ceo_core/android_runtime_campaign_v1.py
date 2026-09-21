from __future__ import annotations
from typing import Any

REQUIRED=(35,36)

def build_runtime_campaign_v1(*,apk_sha256:str,input_identity_sha256:str)->dict[str,Any]:
    return {'schema_version':1,'apk_sha256':apk_sha256,'input_identity_sha256':input_identity_sha256,
            'api_levels':list(REQUIRED),'same_apk_required':True,'install_requires_human_start':True,
            'physical_phone_install_authorized':False,'production_verified':False}

def qualify_runtime_campaign_v1(campaign:dict[str,Any],observations:list[dict[str,Any]])->dict[str,Any]:
    p=[]; by={int(o.get('api_level',-1)):o for o in observations}
    for api in REQUIRED:
        o=by.get(api)
        if not o or o.get('ok') is not True: p.append(f'api{api}_missing_or_failed'); continue
        if o.get('apk_sha256')!=campaign.get('apk_sha256'): p.append(f'api{api}_apk_mismatch')
        if o.get('input_identity_sha256')!=campaign.get('input_identity_sha256'): p.append(f'api{api}_input_mismatch')
    return {'ok':not p,'problems':p,'android_lab_runtime_accepted':not p,'physical_phone_install_authorized':False}
