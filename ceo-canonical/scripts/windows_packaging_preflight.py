from __future__ import annotations
import json, re, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
issues=[]
pyproject=(ROOT/'pyproject.toml').read_text(encoding='utf-8')
main=(ROOT/'ceo_app'/'main.py').read_text(encoding='utf-8')
iss=(ROOT/'packaging'/'windows'/'installer.iss').read_text(encoding='utf-8')
build=(ROOT/'packaging'/'windows'/'build_windows.ps1').read_text(encoding='utf-8')
spec=(ROOT/'packaging'/'windows'/'CEO.spec').read_text(encoding='utf-8')
m_py=re.search(r'version\s*=\s*"([^"]+)"', pyproject)
m_api=re.search(r'version="([^"]+)"', main)
m_iss=re.search(r'#define MyAppVersion "([^"]+)"', iss)
versions={"pyproject":m_py.group(1) if m_py else None,"api":m_api.group(1) if m_api else None,"installer":m_iss.group(1) if m_iss else None}
if versions['pyproject'] != '0.8.0rc0': issues.append(f"pyproject version unexpected: {versions['pyproject']}")
if versions['api'] != '0.8.0-validation-rc': issues.append(f"API version unexpected: {versions['api']}")
if versions['installer'] != '0.8.0-validation-rc': issues.append(f"Installer version unexpected: {versions['installer']}")
required_build=['pytest','security_audit.py','static_check.py','playwright install chromium','PyInstaller']
for token in required_build:
    if token.lower() not in build.lower(): issues.append(f"build script missing {token}")
required_spec_patterns=["'ceo_app' / 'main.py'", "'ceo_app'/'static'"]
for token in required_spec_patterns:
    if token not in spec: issues.append(f"spec missing pattern {token}")
result={"ok":not issues,"versions":versions,"issues":issues}
print(json.dumps(result, indent=2, ensure_ascii=False))
sys.exit(0 if not issues else 1)
