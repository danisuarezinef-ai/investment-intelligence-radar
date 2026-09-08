from pathlib import Path


def source():
    return Path('radar_desktop_v2.py').read_text(encoding='utf-8')


def test_activity_controls_use_explicit_moving_toggle():
    s=source()
    assert 'class ToggleSwitch' in s
    assert "text='OFF'" in s
    assert "text='ON'" in s
    assert 'pc_toggle.set(r)' in s
    assert 'cloud_toggle.set(enabled)' in s


def test_intelligence_panel_is_collapsible_and_closed_by_default():
    s=source()
    assert 'intel_open=tk.BooleanVar(value=False)' in s
    assert "text='▾ MOSTRAR'" in s
    assert 'intel_body.pack_forget()' in s


def test_simulator_has_separate_activate_deactivate_restart_controls():
    s=source()
    assert "('REINICIAR',sim_restart" in s
    assert "('DESACTIVAR',sim_deactivate" in s
    assert "('ACTIVAR',sim_activate" in s
    assert 'paper_start(value)' in s
    assert 'paper_set_enabled(True)' in s
    assert 'paper_set_enabled(False)' in s


def test_update_button_is_conditional_and_lists_start_collapsed():
    s=source()
    assert "text='ACTUALIZACIÓN'" in s
    assert 'BUSCAR ACTUALIZACIÓN' not in s
    assert 'check_for_update_async()' in s
    assert 'def collapsed_list_card' in s
    assert "collapsed_list_card(body,'Últimos precios · PC local'" in s
    assert "collapsed_list_card(body,'Últimos eventos · PC local'" in s


def test_rankings_have_independent_vertical_scrollbars():
    s=source()
    assert "def scroll_text_card" in s
    assert "sb=tk.Scrollbar(wrap,orient='vertical')" in s
    assert "yscrollcommand=sb.set" in s
    assert "hist_text=scroll_text_card" in s
    assert "opp_text=scroll_text_card" in s
