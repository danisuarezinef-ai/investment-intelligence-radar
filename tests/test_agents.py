import radar_core
import radar_agents as ra


def _use_tmp_db(tmp_path, monkeypatch):
    db = str(tmp_path / 'radar.db')
    monkeypatch.setattr(radar_core, 'DB', db)
    monkeypatch.setattr(radar_core, 'STATUS', str(tmp_path / 'status.json'))
    monkeypatch.setattr(radar_core, 'LOG', str(tmp_path / 'worker.log'))
    monkeypatch.setattr(radar_core, 'PID', str(tmp_path / 'worker.pid'))
    radar_core.init_db()
    ra.init_agents_db()
    return db


def test_five_agents_seeded_with_independent_capital(tmp_path, monkeypatch):
    _use_tmp_db(tmp_path, monkeypatch)
    states = ra.ensure_agents(reset=True, initial_cash=200.0)
    assert len(states) == 5
    assert {s['agent_id'] for s in states} == set(ra.AGENTS)
    assert all(abs(s['initial'] - 200.0) < 1e-9 for s in states)
    assert all(abs(s['cash'] - 200.0) < 1e-9 for s in states)


def test_agent_trade_models_fees_spread_and_fx(tmp_path, monkeypatch):
    _use_tmp_db(tmp_path, monkeypatch)
    ra.ensure_agents(reset=True, initial_cash=200.0)
    monkeypatch.setattr(ra, 'history_ready', lambda: True)
    monkeypatch.setattr(ra, '_latest_prices', lambda: {'MSFT': 100.0, 'NVDA': 50.0, 'ASML': 80.0})
    ranks = {
        'bajo': [
            {'symbol': 'MSFT', 'score': 8.0, 'risk': 'bajo', 'volatility': 12.0},
            {'symbol': 'NVDA', 'score': 6.0, 'risk': 'bajo', 'volatility': 18.0},
        ],
        'intermedio': [
            {'symbol': 'ASML', 'score': 5.0, 'risk': 'intermedio', 'volatility': 28.0},
        ],
        'alto': [],
    }
    monkeypatch.setattr(ra, 'opportunity_rankings', lambda limit=12: ranks)

    st = ra.step_agent('balanced', force=True)
    assert st['invested'] > 0
    assert len(st['positions']) >= 1
    assert len(st['trades']) >= 1
    buy = next(t for t in st['trades'] if t['side'] == 'BUY')
    assert buy['fees'] > 0
    assert buy['spread_cost'] > 0
    assert buy['fx_cost'] > 0
    assert st['cash'] < 200.0


def test_agent_risk_metrics_available(tmp_path, monkeypatch):
    _use_tmp_db(tmp_path, monkeypatch)
    ra.ensure_agents(reset=True, initial_cash=200.0)
    st = ra.agent_status('conservative')
    assert 'drawdown_pct' in st
    assert 'max_drawdown_pct' in st
    assert 'sharpe' in st
