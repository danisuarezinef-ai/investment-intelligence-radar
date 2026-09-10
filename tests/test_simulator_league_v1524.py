import json
from pathlib import Path

import radar_simulator_league_v1 as league
import radar_simulation_desktop_v2 as lab


def _weekdays(n, start_day=1):
    out=[];day=start_day
    while len(out)<n:
        date=f'2026-09-{day:02d}'
        import datetime
        if datetime.date.fromisoformat(date).weekday()<5:out.append(date)
        day+=1
    return out


def test_release_is_v1524_or_newer():
    version=json.loads(Path('version.json').read_text(encoding='utf-8'))['version']
    assert tuple(map(int,version.split('.'))) >= (1,5,24)


def test_league_has_real_risk_ladder_and_comparable_1000_base():
    assert league.DISPLAY_BASE_EQUITY == 1000.0
    assert league.RISK_PROFILES['conservative']['risk_label'] == 'RIESGO --'
    assert league.RISK_PROFILES['balanced']['risk_label'] == 'RIESGO -'
    assert league.RISK_PROFILES['champion']['risk_label'].startswith('RIESGO BASE')
    assert league.RISK_PROFILES['aggressive']['risk_label'] == 'RIESGO +'
    assert league.RISK_PROFILES['high_conviction']['risk_label'] == 'RIESGO ++'
    assert league.RISK_PROFILES['experimental']['risk_label'].startswith('RIESGO +++')
    assert league.normalize_equity(240,200) == 1200.0
    assert league.normalize_equity(101.8,200) == 509.0


def test_aciertos_errores_are_equity_moves_not_prediction_accuracy():
    series=[
        {'normalized_equity':1000},
        {'normalized_equity':1020},
        {'normalized_equity':990},
        {'normalized_equity':990},
        {'normalized_equity':1040},
    ]
    assert league.daily_move_counts(series)=={'up_days':2,'down_days':1,'neutral_days':1}
    source=Path('radar_simulation_desktop_v2.py').read_text(encoding='utf-8')
    assert 'Aciertos = jornadas con subida de equity' in source
    assert 'Errores = jornadas con bajada' in source


def test_promotion_requires_ten_consecutive_observed_weekdays():
    days=_weekdays(10)
    champion=[{'date':d,'normalized_equity':1000+i} for i,d in enumerate(days)]
    challenger=[{'date':d,'normalized_equity':1010+i} for i,d in enumerate(days)]
    assert league.consecutive_lead_days(challenger[:-1],champion[:-1])==9
    assert league.promotion_candidate(9,-3,-2)['eligible'] is False
    assert league.consecutive_lead_days(challenger,champion)==10
    gate=league.promotion_candidate(10,-3,-2)
    assert gate['eligible'] is True
    assert gate['promotion_scope']=='SIMULATION_LEAGUE_ONLY'
    assert gate['automatic_model_promotion'] is False
    assert gate['real_trading'] is False


def test_promotion_risk_guard_blocks_lucky_but_excessive_drawdown():
    gate=league.promotion_candidate(10,-13,-2,risk_guard_pp=10)
    assert gate['eligible'] is False
    assert gate['risk_guard_ok'] is False
    assert gate['days_remaining']==0
    assert gate['real_trading'] is False


def test_cloud_and_desktop_wire_the_isolated_league_endpoint():
    cloud=Path('cloud_service_v3.py').read_text(encoding='utf-8')
    desktop=Path('radar_simulation_desktop_v2.py').read_text(encoding='utf-8')
    assert "'/simulator-league-v1'" in cloud
    assert lab._CLOUD_ENDPOINTS['league']=='/simulator-league-v1'
    assert 'push_league_snapshot' in cloud
    assert 'league_status' in cloud
    assert 'Liga PAPER · Champion vs Challengers' in desktop
    assert 'base comparable 1.000 €' in desktop
    assert 'faltan {remaining}' in desktop


def test_supabase_league_is_private_rls_and_cannot_enable_real_trading():
    migration=Path('supabase/migrations/20260910180000_simulator_league_v1.sql').read_text(encoding='utf-8').lower()
    edge=Path('supabase/functions/radar-simulator-league/index.ts').read_text(encoding='utf-8')
    for table in ('radar_simulator_league_daily','radar_simulator_league_state','radar_simulator_league_events'):
        assert f'alter table public.{table} enable row level security' in migration
        assert table in edge
    assert 'revoke all on table public.radar_simulator_league_daily from public, anon, authenticated' in migration
    assert 'grant select, insert, update on table public.radar_simulator_league_daily to service_role' in migration
    assert 'check (real_trading = false)' in migration
    assert 'SIMULATION_LEAGUE_ONLY' in edge
    assert 'automatic_model_promotion:false' in edge
    assert 'live_execution_allowed:false' in edge
    assert 'real_trading:false' in edge
    assert league.REAL_TRADING is False
    assert lab.REAL_TRADING is False


def test_old_champion_becomes_challenger_one_on_league_promotion():
    edge=Path('supabase/functions/radar-simulator-league/index.ts').read_text(encoding='utf-8')
    assert 'const order=unique([old,' in edge
    assert 'champion_key:next.competitor_key' in edge
    assert 'last_promotion_day:today' in edge
