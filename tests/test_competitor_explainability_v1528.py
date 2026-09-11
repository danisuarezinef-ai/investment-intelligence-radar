import json
from pathlib import Path

import radar_autonomous_simulator_v1 as autonomous
import radar_competitor_explainability_v1 as explain
import radar_simulation_desktop_v4 as ui


ROOT = Path(__file__).resolve().parents[1]


def test_release_and_build_use_explainable_lab_v4():
    version = json.loads((ROOT / 'version.json').read_text(encoding='utf-8'))['version']
    assert tuple(map(int, version.split('.'))) >= (1, 5, 28)
    build = (ROOT / 'build_windows.ps1').read_text(encoding='utf-8')
    assert 'RadarSimulationLab radar_simulation_desktop_v4.py' in build


def test_live_detail_normalizes_positions_and_recent_decisions(monkeypatch):
    monkeypatch.setattr(explain, 'champion_status', lambda: {
        'initial': 200.0, 'cash': 100.0, 'invested': 100.0, 'total': 204.0,
        'pnl': 4.0, 'pnl_pct': 2.0,
        'positions': [{'symbol': 'NVDA', 'qty': 1.0, 'avg_price': 95, 'price': 100, 'value': 100, 'pnl_pct': 5.263}],
        'trades': [{'ts': '2026-09-11T18:00:00+00:00', 'symbol': 'NVDA', 'side': 'buy', 'qty': 1, 'price': 95, 'gross': 95, 'costs': .25, 'reason': 'Champion risk-gated'}],
    })
    monkeypatch.setattr(explain, 'agents_status', lambda: [])
    out = explain.competitor_live_details()
    champion = out['competitors']['champion']
    assert out['source'] == 'LIVE_LOCAL_PAPER_ENGINE_READ_ONLY'
    assert champion['positions'][0]['symbol'] == 'NVDA'
    assert champion['recent_decisions'][0]['side'] == 'BUY'
    assert champion['invested_pct'] > 49
    assert out['can_trade'] is False
    assert out['real_trading'] is False


def test_fail_soft_detail_never_breaks_simulator_status_path(monkeypatch):
    monkeypatch.setattr(autonomous, 'competitor_live_details', lambda: (_ for _ in ()).throw(RuntimeError('boom')))
    out = autonomous._competitor_details_fail_soft()
    assert out['status'] == 'DEGRADED'
    assert out['competitors'] == {}
    assert out['can_trade'] is False
    assert out['real_trading'] is False


def test_ui_expanded_text_shows_holdings_and_reason():
    text = ui.live_detail_text({
        'cash': 104.25, 'invested': 95.75, 'invested_pct': 47.875, 'equity': 200.0,
        'positions': [{'symbol': 'MSFT', 'value': 48.0, 'pnl_pct': -0.6, 'avg_price': 420.0, 'price': 417.48}],
        'recent_decisions': [{'side': 'BUY', 'symbol': 'MSFT', 'value': 48.0, 'reason': 'Score 3.20 · riesgo bajo', 'ts': '2026-09-11T20:15:00+00:00'}],
    })
    assert 'CARTERA PAPER EN VIVO' in text
    assert 'MSFT' in text
    assert 'Score 3.20' in text
    assert 'Últimas decisiones' in text
    assert 'autoridad durable sigue en la Liga PAPER' in text


def test_explainability_module_is_observation_only():
    source = (ROOT / 'radar_competitor_explainability_v1.py').read_text(encoding='utf-8')
    for forbidden in ('step_agent(', 'step_champion(', 'paper_start(', 'paper_set_enabled(', 'REAL_TRADING = True'):
        assert forbidden not in source
    assert 'can_trade' in source
    assert 'real_trading' in source


def test_simulator_status_exposes_competitor_details_without_live_authority():
    source = (ROOT / 'radar_autonomous_simulator_v1.py').read_text(encoding='utf-8')
    assert "'competitor_details':competitors" in source
    assert '_competitor_details_fail_soft' in source
    assert "'automatic_live_promotion':False" in source
