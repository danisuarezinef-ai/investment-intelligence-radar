"""Non-weakening wrapper for the legacy pre-1.6 integrity audit.

Runs the original v3-v10 audit unchanged except for virtualizing its obsolete start.sh
expectation, then validates the actual v22 entrypoint and every additive runtime layer
v11-v22 plus PAPER safety locks.
"""
from pathlib import Path
import json
import tools.pre160_integrity_ci as legacy


def audit(root='.'):
    root=Path(root);findings=[]
    original_text=legacy._text
    def compat_text(r,path):
        if str(path)=='start.sh':return '# legacy audit compatibility\nexec python cloud_service_v10.py\n'
        return original_text(r,path)
    legacy._text=compat_text
    try:old=legacy.audit(root)
    finally:legacy._text=original_text
    if old.get('status')!='PASS':findings.extend('LEGACY:'+x for x in old.get('findings') or [])

    start=(root/'start.sh').read_text(encoding='utf-8-sig') if (root/'start.sh').exists() else ''
    if 'exec python cloud_service_v22.py' not in start:findings.append('START_NOT_V22')
    for n in range(11,23):
        p=root/f'cloud_service_v{n}.py'
        if not p.exists():findings.append(f'MISSING_CLOUD_V{n}');continue
        text=p.read_text(encoding='utf-8-sig')
        expected=f'cloud_service_v{n-1}'
        if expected not in text:findings.append(f'V{n}_CHAIN_IMPORT_INVALID:{expected}')
        if 'REAL_TRADING=False' not in text.replace(' ',''):findings.append(f'V{n}_TRADING_BOUNDARY_MISSING')
    required=('radar_operational_closure_101_120_v1.py','radar_learning_governance_121_130_v2.py','radar_paper_certification_131_160_v1.py',
              'tests/test_operational_closure_101_120_v1.py','tests/test_learning_governance_121_130_v1.py','tests/test_paper_certification_131_160_v1.py')
    for path in required:
        if not (root/path).exists():findings.append('MISSING_COMPONENT:'+path)
    cert=(root/'radar_paper_certification_131_160_v1.py').read_text(encoding='utf-8-sig') if (root/'radar_paper_certification_131_160_v1.py').exists() else ''
    compact=cert.replace(' ','')
    for token in ("'automatic_promotion':False","'automatic_release':False","'setup_1_6_allowed':False","'live_execution_allowed':False",'REAL_TRADING=False'):
        if token not in compact:findings.append('CERTIFICATION_SAFETY_TOKEN_MISSING:'+token)
    return {'status':'PASS' if not findings else 'FAIL','findings':findings,'legacy_status':old.get('status'),'actual_entrypoint':'cloud_service_v22.py','real_trading':False}

if __name__=='__main__':
    result=audit();print(json.dumps(result,indent=2,ensure_ascii=False));raise SystemExit(0 if result['status']=='PASS' else 1)
