from pathlib import Path
import radar_simulator_league_v1 as league
import radar_simulator_vscore_v1 as vscore
import radar_paper_engine_persistence_v1 as persistence
import radar_simulation_desktop_v3 as ui


def test_vscore_release_is_paper_only_everywhere():
    assert league.REAL_TRADING is False
    assert vscore.REAL_TRADING is False
    assert persistence.REAL_TRADING is False
    assert ui.REAL_TRADING is False
    cloud=Path('cloud_service_v3.py').read_text(encoding='utf-8')
    edge=Path('supabase/functions/radar-simulator-league/index.ts').read_text(encoding='utf-8')
    checkpoint=Path('supabase/functions/radar-paper-engine-checkpoint/index.ts').read_text(encoding='utf-8')
    assert 'REAL_TRADING=False' in cloud
    assert 'automatic_model_promotion:false' in edge
    assert 'live_execution_allowed:false' in edge
    assert 'can_trade:false' in edge
    assert 'real_trading:false' in edge
    assert 'can_trade:false' in checkpoint
    assert 'real_trading:false' in checkpoint
