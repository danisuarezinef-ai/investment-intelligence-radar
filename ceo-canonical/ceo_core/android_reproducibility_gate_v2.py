from __future__ import annotations
from typing import Any
from .android_build_receipt_v3 import validate_receipt_v3

def qualify_reproducibility_v2(first:dict[str,Any],second:dict[str,Any])->dict[str,Any]:
    a,b=validate_receipt_v3(first),validate_receipt_v3(second); problems=[]
    if not a['ok'] or not b['ok']: problems.append('invalid_receipt')
    if first.get('build_ordinal')!=1 or second.get('build_ordinal')!=2: problems.append('ordinal')
    for k in ('apk_sha256','apk_size','input_identity_sha256','payload_sha256','dependency_graph_sha256','jdk','gradle','compile_sdk','build_tools'):
        if first.get(k)!=second.get(k): problems.append('mismatch_'+k)
    return {'ok':not problems,'problems':problems,'apk_sha256':first.get('apk_sha256') if not problems else None,
            'same_runner_allowed':True,'independent_runner_preferred_for_release':True,'production_verified':False}
