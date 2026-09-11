"""Static backend integrity gate for pre-1.6 work. No Windows packaging required."""
from pathlib import Path
import json


def audit(root='.'):
    root=Path(root);findings=[]
    start=(root/'start.sh').read_text(encoding='utf-8-sig')
    v4=(root/'cloud_service_v4.py').read_text(encoding='utf-8-sig')
    v3=(root/'cloud_service_v3.py').read_text(encoding='utf-8-sig')
    if 'cloud_service_v4.py' not in start:findings.append('START_NOT_V4')
    if 'import cloud_service_v3 as base3' not in v4:findings.append('V4_NOT_COMPOSED_OVER_V3')
    if 'import cloud_service as base' in v4:findings.append('V4_LEGACY_BASE_IMPORT')
    for endpoint in ('/pre160-runtime-v2','/pre160-readiness-v1','/mobile-summary-v2'):
        if endpoint not in v4:findings.append('MISSING_V4_ENDPOINT:'+endpoint)
    for endpoint in ('/pre160-evaluation-v1','/simulator-league-v1','/persistent-authority-v1'):
        if endpoint not in v3:findings.append('MISSING_V3_ENDPOINT:'+endpoint)
    if 'REAL_TRADING=False' not in v4.replace(' ',''):findings.append('V4_TRADING_BOUNDARY_MISSING')
    version=json.loads((root/'version.json').read_text(encoding='utf-8-sig')).get('version')
    return {'status':'PASS' if not findings else 'FAIL','version':version,'findings':findings,'setup_built':False,'real_trading':False}


if __name__=='__main__':
    result=audit();print(json.dumps(result,indent=2,ensure_ascii=False));raise SystemExit(0 if result['status']=='PASS' else 1)
