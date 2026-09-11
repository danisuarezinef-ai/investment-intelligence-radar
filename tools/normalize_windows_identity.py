from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRODUCTS = (
    'InvestmentIntelligenceRadarDesktop',
    'InvestmentIntelligenceRadarDesktopSync',
    'RadarSimulationLab',
)
TEXT_FILES = (
    'radar_desktop_v2.py',
    'radar_desktop_v3.py',
    'radar_simulation_desktop.py',
    'radar_pc_sync_hook.py',
)


def read_version(root: Path = ROOT) -> str:
    version = str(json.loads((root / 'version.json').read_text(encoding='utf-8-sig'))['version']).strip()
    if not version:
        raise RuntimeError('version.json missing version')
    return version


def normalize_text(text: str, version: str) -> str:
    for product in PRODUCTS:
        text = re.sub(
            re.escape(product) + r'/\d+(?:\.\d+)*',
            f'{product}/{version}',
            text,
        )
    text = re.sub(r"APP_VERSION\s*=\s*'[^']+'", f"APP_VERSION = '{version}'", text)
    text = re.sub(r"PC_SYNC_VERSION\s*=\s*'[^']+'", f"PC_SYNC_VERSION = '{version}'", text)
    return text


def stale_identities(text: str, version: str) -> list[str]:
    stale: list[str] = []
    for product in PRODUCTS:
        for found in re.findall(re.escape(product) + r'/(\d+(?:\.\d+)*)', text):
            if found != version:
                stale.append(f'{product}/{found}')
    return stale


def main(root: Path = ROOT) -> None:
    version = read_version(root)
    for relative in TEXT_FILES:
        path = root / relative
        if not path.exists():
            continue
        original = path.read_text(encoding='utf-8-sig')
        normalized = normalize_text(original, version)
        if normalized != original:
            path.write_text(normalized, encoding='utf-8', newline='\n')

    for relative in TEXT_FILES:
        path = root / relative
        if not path.exists():
            continue
        stale = stale_identities(path.read_text(encoding='utf-8'), version)
        if stale:
            raise RuntimeError(f'stale runtime identity in {path.name}: {stale}')

    print(f'Windows runtime identity normalized to {version}')


if __name__ == '__main__':
    main()
