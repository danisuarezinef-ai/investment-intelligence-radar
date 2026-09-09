from pathlib import Path


def test_update_button_is_not_conditionally_hidden():
    text=Path('radar_desktop_v2.py').read_text(encoding='utf-8')
    assert "update_btn.pack_forget()" not in text
    assert "BUSCAR ACTUALIZACIÓN" in text


def test_update_check_is_periodic_and_user_visible():
    text=Path('radar_desktop_v2.py').read_text(encoding='utf-8')
    assert 'UPDATE_CHECK_INTERVAL_MS' in text
    assert 'root.after(UPDATE_CHECK_INTERVAL_MS' in text
    assert 'last_update_check' in text


def test_update_check_does_not_swallow_errors_silently():
    text=Path('radar_desktop_v2.py').read_text(encoding='utf-8')
    assert 'update_status' in text
    assert 'No se pudo comprobar la actualización' in text
