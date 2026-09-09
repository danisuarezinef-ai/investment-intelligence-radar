from pathlib import Path


def test_update_control_is_always_visible():
    text=Path('radar_desktop_v3.py').read_text(encoding='utf-8')
    assert "BUSCAR ACTUALIZACIÓN" in text
    assert 'tk.Button.pack_forget=_button_forget' in text
    assert "pack(side='right',anchor='n')" in text


def test_update_check_runs_periodically_while_open():
    text=Path('radar_desktop_v3.py').read_text(encoding='utf-8')
    assert '_UPDATE_CHECK_INTERVAL_MS=5*60*1000' in text
    assert 'self.after(_UPDATE_CHECK_INTERVAL_MS,periodic)' in text
    assert 'self.after(1000,periodic)' in text


def test_update_state_is_reflected_on_the_button():
    text=Path('radar_desktop_v3.py').read_text(encoding='utf-8')
    assert "ACTUALIZAR A v{remote}" in text
    assert "ACTUALIZADO · v{local}" in text
    assert "ERROR · REINTENTAR" in text
    assert "Cache-Control':'no-cache'" in text


def test_manual_update_first_checks_then_launches_only_when_available():
    text=Path('radar_desktop_v3.py').read_text(encoding='utf-8')
    assert 'def _manual_update(button):' in text
    assert "text.startswith('ACTUALIZAR A v')" in text
    assert '_check_update(button.winfo_toplevel(),manual=True)' in text
    assert "self._radar_launch_updater=launch" in text
