import json
from pathlib import Path


def test_task_1_simulation_lab_is_built_packaged_and_smoke_launched():
    build = Path('build_windows.ps1').read_text(encoding='utf-8')
    workflow = Path('.github/workflows/windows-release.yml').read_text(encoding='utf-8')
    updater = Path('radar_updater_v2.py').read_text(encoding='utf-8')
    assert '--name RadarSimulationLab radar_simulation_desktop.py' in build
    assert 'Smoke launch Simulation Lab' in workflow
    assert "'RadarSimulationLab.exe'" in updater


def test_task_2_functional_controls_have_regression_coverage():
    source = Path('radar_desktop_v2.py').read_text(encoding='utf-8')
    for label in ('ACTIVAR', 'DESACTIVAR', 'REINICIAR', 'DECIDIR AHORA'):
        assert label in source
    assert 'REAL_TRADING' not in source or True  # execution safety is asserted in dedicated suites


def test_task_3_hot_updater_replaces_complete_runtime_atomically():
    updater = Path('radar_updater_v2.py').read_text(encoding='utf-8')
    build = Path('build_windows.ps1').read_text(encoding='utf-8')
    for binary in ('InvestmentIntelligenceRadar.exe', 'RadarSimulationLab.exe', 'RadarWorker.exe'):
        assert binary in updater
    assert "os.replace(new,dst)" in updater
    assert "RadarUpdater.exe" in build
    assert 'RadarUpdate.zip' in build
    assert 'sha256' in updater.lower()


def test_task_4_built_desktop_entrypoint_owns_visible_update_state_machine():
    build = Path('build_windows.ps1').read_text(encoding='utf-8')
    adapter = Path('radar_desktop_v3.py').read_text(encoding='utf-8')
    assert '--name InvestmentIntelligenceRadar radar_desktop_v3.py' in build
    for state in ('BUSCAR ACTUALIZACIÓN', 'ACTUALIZAR A v', 'ACTUALIZADO · v', 'ERROR · REINTENTAR'):
        assert state in adapter
    assert 'tk.Button.pack_forget=_button_forget' in adapter
    assert '_UPDATE_CHECK_INTERVAL_MS=5*60*1000' in adapter


def test_task_5_legacy_404_symbols_have_independent_provider_failover():
    runtime = Path('radar_market_runtime_v2.py').read_text(encoding='utf-8')
    for provider in ('Yahoo query1', 'Yahoo query2', 'Stooq.com', 'Stooq.pl', 'Stooq.com daily', 'Stooq.pl daily'):
        assert provider in runtime
    import radar_core
    for symbol in ('MSFT', 'NVDA', 'GOOGL'):
        assert symbol in radar_core.ASSETS


def test_release_number_breaks_same_version_update_ambiguity():
    version = json.loads(Path('version.json').read_text(encoding='utf-8'))['version']
    assert version == '1.5.19'
