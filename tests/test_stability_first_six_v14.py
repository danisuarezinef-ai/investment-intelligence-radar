import json
from pathlib import Path


def test_cloud_sync_hook_requests_all_operational_endpoints():
    text=Path('radar_pc_sync_hook.py').read_text(encoding='utf-8')
    for endpoint in ('/priority-v1','/operational-pipeline-v1','/market-telemetry-v1','/ops-health','/node-heartbeat','/pc-sync'):
        assert endpoint in text


def test_market_runtime_has_independent_fallbacks_for_legacy_404s():
    text=Path('radar_market_runtime_v2.py').read_text(encoding='utf-8')
    assert "Yahoo query1" in text
    assert "Yahoo query2" in text
    assert "Stooq.com" in text
    assert "Stooq.pl" in text
    assert "Stooq.com daily" in text
    assert "Stooq.pl daily" in text
    assert 'for symbol, code in core.ASSETS.items()' in text


def test_principal_assets_include_original_404_symbols():
    import radar_core
    for symbol in ('MSFT','NVDA','GOOGL'):
        assert symbol in radar_core.ASSETS


def test_simulation_lab_is_packaged_and_smoke_tested_on_windows():
    workflow=Path('.github/workflows/windows-release.yml').read_text(encoding='utf-8')
    build=Path('build_windows.ps1').read_text(encoding='utf-8')
    assert 'Smoke launch Simulation Lab' in workflow
    assert 'RadarSimulationLab.exe' in workflow
    assert '--name RadarSimulationLab' in build
    assert 'dist\\RadarSimulationLab.exe' in build


def test_installer_owns_radar_process_shutdown_instead_of_partial_continue():
    installer=Path('installer/Radar.iss').read_text(encoding='utf-8')
    assert 'CloseApplications=no' in installer
    assert 'PrepareToInstall' in installer
    for proc in ('InvestmentIntelligenceRadar.exe','RadarSimulationLab.exe','RadarWorker.exe','RadarUpdater.exe'):
        assert proc in installer
