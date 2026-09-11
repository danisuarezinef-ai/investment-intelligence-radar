import json
import re
from pathlib import Path

from tools.normalize_windows_identity import PRODUCTS, TEXT_FILES, normalize_text, stale_identities


ROOT = Path(__file__).resolve().parents[1]
VERSION = str(json.loads((ROOT / 'version.json').read_text(encoding='utf-8-sig'))['version'])


def _version_tuple(value):
    return tuple(int(part) for part in str(value).split('.'))


def test_release_is_at_least_v1527_and_installer_matches():
    assert _version_tuple(VERSION) >= (1, 5, 27)
    installer = (ROOT / 'installer' / 'Radar.iss').read_text(encoding='utf-8')
    assert f'#define MyAppVersion "{VERSION}"' in installer


def test_normalizer_rewrites_stale_desktop_user_agents():
    sample = (
        "InvestmentIntelligenceRadarDesktop/1.3 "
        "InvestmentIntelligenceRadarDesktopSync/1.5.21 "
        "RadarSimulationLab/1.5.22"
    )
    normalized = normalize_text(sample, VERSION)
    for product in PRODUCTS:
        assert f'{product}/{VERSION}' in normalized
    assert stale_identities(normalized, VERSION) == []


def test_all_packaged_sources_normalize_to_one_release_identity():
    for relative in TEXT_FILES:
        path = ROOT / relative
        if not path.exists():
            continue
        normalized = normalize_text(path.read_text(encoding='utf-8-sig'), VERSION)
        assert stale_identities(normalized, VERSION) == [], relative


def test_normalizer_covers_hardcoded_desktop_versions_present_in_legacy_sources():
    source = (ROOT / 'radar_desktop_v2.py').read_text(encoding='utf-8-sig')
    assert re.search(r'InvestmentIntelligenceRadarDesktop/\d', source)
    normalized = normalize_text(source, VERSION)
    found = re.findall(r'InvestmentIntelligenceRadarDesktop/(\d+(?:\.\d+)*)', normalized)
    assert found
    assert set(found) == {VERSION}


def test_windows_workflow_runs_identity_normalization_before_tests():
    workflow = (ROOT / '.github' / 'workflows' / 'windows-release.yml').read_text(encoding='utf-8')
    normalize_at = workflow.index('Normalize runtime identity')
    test_at = workflow.index('Test core')
    build_at = workflow.index('Build application, updater and Setup.exe')
    assert normalize_at < test_at < build_at
    assert 'python tools/normalize_windows_identity.py' in workflow
