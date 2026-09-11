from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = str(json.loads((ROOT / 'version.json').read_text(encoding='utf-8-sig'))['version']).strip()
if not VERSION:
    raise RuntimeError('version.json missing version')

TEXT_FILES = [
    ROOT / 'radar_desktop_v2.py',
    ROOT / 'radar_desktop_v3.py',
    ROOT / 'radar_simulation_desktop.py',
    ROOT / 'radar_pc_sync_hook.py',
]

UA_PATTERNS = [
    (re.compile(r'InvestmentIntelligenceRadarDesktop/\d+(?:\.\d+)*'), f'InvestmentIntelligenceRadarDesktop/{VERSION}'),
    (re.compile(r'InvestmentIntelligenceRadarDesktopSync/\d+(?:\.\d+)*'), f'InvestmentIntelligenceRadarDesktopSync/{VERSION}'),
    (re.compile(r'RadarSimulationLab/\d+(?:\.\d+)*'), f'RadarSimulationLab/{VERSION}'),
]

VERSION_PATTERNS = [
    (re.compile(r"APP_VERSION\s*=\s*'[^']+'"), f"APP_VERSION = '{VERSION}'"),
    (re.compile(r"PC_SYNC_VERSION\s*=\s*'[^']+'"), f"PC_SYNC_VERSION = '{VERSION}'"),
]

for path in TEXT_FILES:
    if not path.exists():
        continue
    text = path.read_text(encoding='utf-8-sig')
    original = text
    for pattern, replacement in UA_PATTERNS:
        text = pattern.sub(replacement, text)
    for pattern, replacement in VERSION_PATTERNS:
        text = pattern.sub(replacement, text)
    if text != original:
        path.write_text(text, encoding='utf-8', newline='\n')

# Fail closed if any packaged desktop file still contains a fixed, mismatched version.
for path in TEXT_FILES:
    if not path.exists():
        continue
    text = path.read_text(encoding='utf-8')
    for product in ('InvestmentIntelligenceRadarDesktop', 'InvestmentIntelligenceRadarDesktopSync', 'RadarSimulationLab'):
        for found in re.findall(re.escape(product) + r'/(\d+(?:\.\d+)*)', text):
            if found != VERSION:
                raise RuntimeError(f'stale runtime identity in {path.name}: {product}/{found} != {VERSION}')

print(f'Windows runtime identity normalized to {VERSION}')
