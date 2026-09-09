from pathlib import Path


def test_update_control_is_always_visible():
    text=Path('radar_desktop_v3.py').read_text(encoding='utf-8')
    assert "BUSCAR ACTUALIZACIÓN" in text
    assert 'tk.Button.pack_forget=_button_forget' in text
    assert 'btn.pack(side=\'right\',anchor=\'n\')' in text


def test_update_check_runs_periodically_while_open():
    text=Path('radar_desktop_v3.py').read_text(encoding='utf-8')
    assert '_UPDATE_CHECK_INTERVAL_MS=5*60*1000' in text
    assert 'self.after(_UPDATE_CHECK_INTERVAL_MS,periodic)' in text
    assert 'self.after(1000,periodic)' in text


def test_update_state_is_reflected_on_the_button():
    text=Path('radar_desktop_v3.py').read_text(encoding='utf-8')
    assert "ACTUALIZAR A v{remote}" in text
    assert "BUSCAR ACTUALIZACIÓN" in text
    assert "Cache-Control':'no-cache'" in text
