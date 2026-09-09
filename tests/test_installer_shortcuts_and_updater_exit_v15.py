from pathlib import Path


def test_installer_cleans_legacy_desktop_shortcuts_and_creates_one_primary_shortcut():
    text = Path('installer/Radar.iss').read_text(encoding='utf-8')
    assert '[InstallDelete]' in text
    assert 'Investment Intelligence Radar.lnk' in text
    assert 'Radar de InversiÃ³n.lnk' in text or 'Radar de InversiÃƒÂ³n.lnk' in text
    assert 'Radar de Inversión.lnk' in text
    # Desktop should only create the main Radar shortcut.
    desktop_icons = [line for line in text.splitlines() if line.strip().startswith('Name: "{autodesktop}')]
    assert len(desktop_icons) == 1
    assert 'Radar de Inversión' in desktop_icons[0]


def test_updater_exits_cleanly_when_already_current():
    text = Path('radar_updater_v2.py').read_text(encoding='utf-8')
    assert 'already_current' in text
    assert 'root.after' in text
    assert 'root.destroy' in text
    assert 'ACTUALIZADO' in text
