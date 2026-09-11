from pathlib import Path


def test_simulation_lab_cockpit_is_built_and_packaged():
    build=Path('build_windows.ps1').read_text(encoding='utf-8')
    updater=Path('radar_updater_v2.py').read_text(encoding='utf-8')
    assert '--name RadarSimulationLab ' in build
    assert ('radar_simulation_desktop_v3.py' in build or 'radar_simulation_desktop_v4.py' in build)
    assert 'RadarSimulationLab.exe' in updater
    assert 'RadarSimulationLab.exe' in build


def test_cockpit_keeps_cloud_authority_and_never_starts_second_writer():
    v3=Path('radar_simulation_desktop_v3.py').read_text(encoding='utf-8')
    assert 'legacy.CloudAwareLab' in v3
    assert 'VScoreLab' in v3
    assert 'autonomous_simulator_loop' not in v3
    assert 'REAL_TRADING = False' in v3
    if Path('radar_simulation_desktop_v4.py').exists():
        v4=Path('radar_simulation_desktop_v4.py').read_text(encoding='utf-8')
        assert 'cockpit.VScoreLab' in v4
        assert 'autonomous_simulator_loop' not in v4
        assert 'REAL_TRADING = False' in v4
