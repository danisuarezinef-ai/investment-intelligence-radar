"""Static pre-1.6 debt audit: stale release pins, trading boundary and entrypoint locks.

Adversarial test fixtures may intentionally contain ``REAL_TRADING=True`` to prove
fail-closed behavior; only executable/config code can raise the critical trading flag.
"""
from __future__ import annotations
from pathlib import Path
import re,json

PRODUCTS=('InvestmentIntelligenceRadarDesktop','InvestmentIntelligenceRadarDesktopSync','RadarSimulationLab')
SELF=Path(__file__).name


def audit(root='.'):
    root=Path(root);version=json.loads((root/'version.json').read_text(encoding='utf-8-sig'))['version']
    findings=[];paths=list(root.glob('*.py'))+list((root/'tests').glob('*.py'))+list((root/'tools').glob('*.py'))
    for path in paths:
        text=path.read_text(encoding='utf-8-sig',errors='replace');is_test=path.parent.name=='tests';is_self=path.parent.name=='tools' and path.name==SELF
        if not is_self and re.search(r'REAL_TRADING\s*=\s*True',text):
            findings.append({'severity':'LOW' if is_test else 'CRITICAL',
                             'code':'ADVERSARIAL_REAL_TRADING_TEST_LITERAL' if is_test else 'REAL_TRADING_TRUE',
                             'path':str(path)})
        if is_test:
            for m in re.finditer(r"VERSION\s*==\s*['\"](1\.\d+\.\d+)['\"]|version\s*==\s*['\"](1\.\d+\.\d+)['\"]",text):
                findings.append({'severity':'MEDIUM','code':'FIXED_VERSION_TEST','path':str(path),'value':next(x for x in m.groups() if x)})
            for m in re.finditer(r'radar_simulation_desktop_v(\d+)\.py',text):
                context=text[max(0,m.start()-120):m.end()+120]
                if 'or ' not in context and '>= ' not in context:
                    findings.append({'severity':'LOW','code':'ENTRYPOINT_PIN','path':str(path),'value':m.group(0)})
        for product in PRODUCTS:
            for m in re.finditer(re.escape(product)+r'/(\d+(?:\.\d+)+)',text):
                if m.group(1)!=version and path.name!='normalize_windows_identity.py':
                    findings.append({'severity':'LOW','code':'STALE_RUNTIME_IDENTITY_LITERAL','path':str(path),'value':m.group(0)})
    unique=[];seen=set()
    for row in findings:
        key=tuple(sorted(row.items()))
        if key not in seen:seen.add(key);unique.append(row)
    return {'version':version,'findings':unique,'critical':sum(x['severity']=='CRITICAL' for x in unique),
            'medium':sum(x['severity']=='MEDIUM' for x in unique),'low':sum(x['severity']=='LOW' for x in unique)}


if __name__=='__main__':
    result=audit();print(json.dumps(result,indent=2,ensure_ascii=False));raise SystemExit(1 if result['critical'] else 0)
