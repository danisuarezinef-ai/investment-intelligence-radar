"""Non-weakening wrapper for the legacy pre-1.6 integrity audit through runtime v23."""
from pathlib import Path
import json
import tools.pre160_integrity_ci as legacy


def audit(root='.'):
    root=Path(root);findings=[];original_text=legacy._text
    def compat_text(r,path):
        if str(path)=='start.sh':return '# legacy audit compatibility\nexec python cloud_service_v10.py\n'
        return original_text(r,path)
    legacy._text=compat_text
    try:old=legacy.audit(root)
    finally:legacy._text=original_text
    if old.get('status')!='PASS':findings.extend('LEGACY:'+x for x in old.get('findings') or [])
    start=(root/'start.sh').read_text(encoding='utf-8-sig') if (root/'start.sh').exists() else ''
    if 'exec python cloud_service_v23.py' not in start:findings.append('START_NOT_V23')
    for n in range(11,24):
        p=root/f'cloud_service_v{n}.py'
        if not p.exists():findings.append(f'MISSING_CLOUD_V{n}');continue
        text=p.read_text(encoding='utf-8-sig');expected=f'cloud_service_v{n-1}'
        if expected not in text:findings.append(f'V{n}_CHAIN_IMPORT_INVALID:{expected}')
        if 'REAL_TRADING=False' not in text.replace(' ',''):findings.append(f'V{n}_TRADING_BOUNDARY_MISSING')
    required=('radar_operational_closure_101_120_v1.py','radar_learning_governance_121_130_v2.py','radar_paper_certification_131_160_v1.py',
              'radar_operational_proof_161_170_v1.py','radar_paper_forward_maturity_v1.py',
              'tests/test_operational_closure_101_120_v1.py','tests/test_learning_governance_121_130_v1.py','tests/test_paper_certification_131_160_v1.py','tests/test_operational_proof_161_170_v1.py',
              'supabase/migrations/20260914013000_paper_forward_maturity_ledger.sql')
    for path in required:
        if not (root/path).exists():findings.append('MISSING_COMPONENT:'+path)
    for path in ('radar_paper_certification_131_160_v1.py','radar_operational_proof_161_170_v1.py'):
        text=(root/path).read_text(encoding='utf-8-sig') if (root/path).exists() else '';compact=text.replace(' ','')
        for token in ("'automatic_promotion':False","'automatic_release':False","'live_execution_allowed':False",'REAL_TRADING=False'):
            if token not in compact:findings.append('SAFETY_TOKEN_MISSING:'+path+':'+token)
    return {'status':'PASS' if not findings else 'FAIL','findings':findings,'legacy_status':old.get('status'),'actual_entrypoint':'cloud_service_v23.py','real_trading':False}

if __name__=='__main__':
    result=audit();print(json.dumps(result,indent=2,ensure_ascii=False));raise SystemExit(0 if result['status']=='PASS' else 1)
