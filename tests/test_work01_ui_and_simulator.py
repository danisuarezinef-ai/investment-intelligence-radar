from datetime import datetime, timedelta, timezone

import pytest

import radar_core
from radar_ui_state import switch_view, update_available, version_key


def _db(tmp_path, monkeypatch):
    monkeypatch.setattr(radar_core, 'DB', str(tmp_path / 'radar.db'))
    monkeypatch.setattr(radar_core, 'STATUS', str(tmp_path / 'status.json'))
    monkeypatch.setattr(radar_core, 'LOG', str(tmp_path / 'worker.log'))
    monkeypatch.setattr(radar_core, 'PID', str(tmp_path / 'worker.pid'))
    radar_core.init_db()


def _seed(tmp_path, monkeypatch, days=45):
    _db(tmp_path, monkeypatch)
    c = radar_core.con()
    start = datetime.now(timezone.utc) - timedelta(days=days)
    for offset, symbol in enumerate(radar_core.ASSETS):
        for day in range(days):
            c.execute(
                'insert into market_snapshots(ts,symbol,price,volume,source) values(?,?,?,?,?)',
                ((start + timedelta(days=day)).isoformat(), symbol, 100 + offset + day, 1, 'Test Historical'),
            )
    c.commit(); c.close()


def test_semantic_version_comparison():
    assert version_key('1.10.0') > version_key('1.9.0')
    assert update_available('1.9.0', '1.10.0') is True
    assert update_available('1.10.0', '1.10') is False
    with pytest.raises(ValueError):
        version_key('latest')


def test_switch_view_represents_real_state_and_unknown():
    assert switch_view(True)['selected'] is True
    assert switch_view(True)['text'].endswith('ON')
    assert switch_view(False)['selected'] is False
    assert switch_view(False)['text'].startswith('OFF')
    assert switch_view(None)['selected'] is None


def test_paper_activate_and_deactivate_preserve_portfolio(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch)
    started = radar_core.paper_start(1000)
    before = (started['cash'], started['total'], started['positions'], started['trades'])
    stopped = radar_core.paper_set_enabled(False)
    assert stopped['enabled'] is False
    assert (stopped['cash'], stopped['total'], stopped['positions'], stopped['trades']) == before
    resumed = radar_core.paper_set_enabled(True)
    assert resumed['enabled'] is True
    assert (resumed['cash'], resumed['total'], resumed['positions'], resumed['trades']) == before


def test_paper_reset_uses_new_capital_and_clears_active_portfolio(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch)
    radar_core.paper_start(1000)
    reset = radar_core.paper_start(2400)
    assert reset['initial'] == 2400
    assert reset['enabled'] is True
    assert reset['cash'] + reset['invested'] == pytest.approx(reset['total'])
    assert reset['total'] == pytest.approx(2400)


def test_step_is_noop_while_disabled(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch)
    radar_core.paper_start(1000)
    before = radar_core.paper_set_enabled(False)
    after = radar_core.paper_step(force=True)
    assert after == before


def test_real_trading_remains_off():
    import radar_continuous_brain
    assert radar_continuous_brain.REAL_TRADING is False


def test_canonical_desktop_source_has_required_collapsed_controls():
    source = open('radar_desktop_v2.py', encoding='utf-8').read()
    assert "text='ACTUALIZACIÓN'" in source
    assert 'BUSCAR ACTUALIZACIÓN' not in source
    for label in ('ACTIVAR', 'DESACTIVAR', 'REINICIAR', 'DECIDIR AHORA'):
        assert "text='" + label + "'" in source
    assert 'check_for_update_async()' in source
    assert source.count('MOSTRAR') >= 2
