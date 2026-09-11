"""Static pre-1.6 debt audit: stale release pins, trading boundary and entrypoint locks."""
from __future__ import annotations
from pathlib import Path
import re,json

PRODUCTS=('InvestmentIntelligenceRadarDesktop','InvestmentIntelligenceRadarDesktopSync','RadarSimulationLab')


def audit(root='.'): 
    root=Path(root);version=json.loads((root/'version.json').read_text(encoding='utf-8-sig'))['version']
    findings=[]
    for path in list(root.glob('*.py'))+list((root/'tests').glob('*.py'))+list((root/'tools').glob('*.py')):
        text=path.read_text(encoding='utf-8-sig',errors='replace')
        if re.search(r'REAL_TRADING\s*=\s*True',text):findings.append({'severity':'CRITICAL','code':'REAL_TRADING_TRUE','path':str(path)})
        if path.parent.name=='tests':
            for m in re.finditer(r"VERSION\s*==\s*['\"](1\.\d+\.\d+)['\"]|version\s*==\s*['\"](1\.\d+\.\d+)['\"]",text):
                findings.append({'severity':'MEDIUM','code':'FIXED_VERSION_TEST','path':str(path),'value':next(x for x in m.groups() if x)})
            for m in re.finditer(r'radar_simulation_desktop_v(\d+)\.py',text):
                if 'or ' not in text[max(0,m.start()-120):m.end()+120] and '>= ' not in text[max(0,m.start()-120):m.end()+120]:
                    findings.append({'severity':'LOW','code':'ENTRYPOINT_PIN','path':str(path),'value':m.group(0)})
        for product in PRODUCTS:
            for m in re.finditer(re.escape(product)+r'/(\d+(?:\.\d+)+)',text):
                if m.group(1)!=version and path.name!='normalize_windows_identity.py':
                    findings.append({'severity':'LOW','code':'STALE_RUNTIME_IDENTITY_LITERAL','path':str(path),'value':m.group(0)})
    return {'version':version,'findings':findings,'critical':sum(x['severity']=='CRITICAL' for x in findings),
            'medium':sum(x['severity']=='MEDIUM' for x in findings),'low':sum(x['severity']=='LOW' for x in findings)}


if __name__=='__main__':
    result=audit();print(json.dumps(result,indent=2,ensure_ascii=False));raise SystemExit(1 if result['critical'] else 0)
