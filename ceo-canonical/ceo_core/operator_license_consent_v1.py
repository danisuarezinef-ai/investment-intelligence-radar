from __future__ import annotations
import hashlib, json, re
from typing import Any

SCOPE='android_sdk_development_toolchain_only'

def _sha(obj:Any)->str:
    return hashlib.sha256(json.dumps(obj,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def build_operator_consent_v1(*,accepted_at:str,operator_statement:str,scope:str=SCOPE)->dict[str,Any]:
    row={'schema_version':1,'operator_explicit_consent':True,'accepted_at':str(accepted_at).strip(),
         'operator_statement':str(operator_statement).strip(),'scope':scope,'licenses_materialized':False,
         'production_authority':False,'publication_authority':False,'spending_authority':False}
    row['consent_sha256']=_sha(row)
    return row

def validate_operator_consent_v1(row:dict[str,Any])->dict[str,Any]:
    problems=[]
    if row.get('schema_version')!=1: problems.append('schema')
    if row.get('operator_explicit_consent') is not True: problems.append('explicit_consent')
    if row.get('scope')!=SCOPE: problems.append('scope')
    if not str(row.get('accepted_at') or '').strip(): problems.append('accepted_at')
    if len(str(row.get('operator_statement') or '').strip())<3: problems.append('statement')
    got=str(row.get('consent_sha256') or '')
    base=dict(row); base.pop('consent_sha256',None)
    if not re.fullmatch(r'[0-9a-f]{64}',got) or got!=_sha(base): problems.append('digest')
    for k in ('production_authority','publication_authority','spending_authority'):
        if row.get(k) is not False: problems.append(k)
    return {'ok':not problems,'problems':problems,'licenses_materialized':bool(row.get('licenses_materialized',False))}
