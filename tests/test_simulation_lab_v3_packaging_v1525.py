from pathlib import Path


def test_simulation_lab_v3_is_built_and_packaged():
    build=Path('build_windows.ps1').read_text(encoding='utf-8')
    updater=Path('radar_updater_v2.py').read_text(encoding='utf-8')
    assert '--name RadarSimulationLab radar_simulation_desktop_v3.py' in build
    assert 'RadarSimulationLab.exe' in updater
    assert 'RadarSimulationLab.exe' in build


def test_v3_keeps_cloud_authority_and_never_starts_second_writer():
    source=Path('radar_simulation_desktop_v3.py').read_text(encoding='utf-8')
    assert 'legacy.CloudAwareLab' in source
    assert 'VScoreLab' in source
    assert 'autonomous_simulator_loop' not in source
    assert 'REAL_TRADING = False' in source
