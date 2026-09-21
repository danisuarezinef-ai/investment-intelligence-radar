from __future__ import annotations
import hashlib, json, re
from typing import Any

def build_receipt_v3(*,ordinal:int,apk_sha256:str,apk_size:int,input_identity_sha256:str,payload_sha256:str,
                     dependency_graph_sha256:str,runner_fingerprint_sha256:str,jdk:str='17',gradle:str='9.4.1')->dict[str,Any]:
    row={'schema_version':3,'build_ordinal':int(ordinal),'apk_sha256':apk_sha256,'apk_size':int(apk_size),
         'input_identity_sha256':input_identity_sha256,'payload_sha256':payload_sha256,
         'dependency_graph_sha256':dependency_graph_sha256,'runner_fingerprint_sha256':runner_fingerprint_sha256,
         'jdk':jdk,'gradle':gradle,'compile_sdk':37,'build_tools':'37.0.0','debug_only':True}
    row['receipt_sha256']=hashlib.sha256(json.dumps(row,sort_keys=True,separators=(',',':')).encode()).hexdigest(); return row

def validate_receipt_v3(r:dict[str,Any])->dict[str,Any]:
    p=[]
    for k in ('apk_sha256','input_identity_sha256','payload_sha256','dependency_graph_sha256','runner_fingerprint_sha256','receipt_sha256'):
        if not re.fullmatch(r'[0-9a-f]{64}',str(r.get(k) or '')): p.append(k)
    base=dict(r); got=base.pop('receipt_sha256',None); exp=hashlib.sha256(json.dumps(base,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    if got!=exp: p.append('receipt_digest')
    if r.get('jdk')!='17' or r.get('gradle')!='9.4.1' or r.get('compile_sdk')!=37 or r.get('build_tools')!='37.0.0': p.append('toolchain')
    if r.get('debug_only') is not True or int(r.get('apk_size') or 0)<=0: p.append('artifact')
    return {'ok':not p,'problems':p}
