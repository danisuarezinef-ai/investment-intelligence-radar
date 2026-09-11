import json
from pathlib import Path

import radar_simulator_vscore_v1 as vscore
import radar_simulator_league_v1 as league
import radar_simulation_desktop_v3 as ui


def test_release_is_v1525_or_newer():
    version=json.loads(Path('version.json').read_text(encoding='utf-8'))['version']
    assert tuple(map(int,version.split('.'))) >= (1,5,25)


def test_vscore_contracts_low_evidence_toward_neutral_200():
    status={'initial':200,'total':230,'invested':120,'max_drawdown_pct':-2,'sharpe':3.0,'marks':1}
    low=vscore.compute_v_score(status,[{'date':'2026-09-10','equity':230}],trade_count=1,distinct_symbols=1,target_invested_pct=70)
    assert 180 <= low['v_score'] <= 260
    assert low['v_confidence'] < .35
    assert low['generalization_status']=='PROXY_UNTIL_REGIME_LINKAGE'
    assert low['real_trading'] is False


def test_vscore_rewards_observed_quality_but_penalizes_bad_risk():
    series=[{'date':f'2026-08-{d:02d}','equity':200+d*1.6} for d in range(1,21)]
    good=vscore.compute_v_score({'initial':200,'total':232,'invested':140,'max_drawdown_pct':-3,'sharpe':2.2,'marks':120},series,trade_count=30,distinct_symbols=8,target_invested_pct=70)
    bad=vscore.compute_v_score({'initial':200,'total':232,'invested':195,'max_drawdown_pct':-24,'sharpe':.2,'marks':120},series,trade_count=30,distinct_symbols=8,target_invested_pct=70)
    assert good['v_score'] > bad['v_score']
    assert good['v_components']['risk_control'] > bad['v_components']['risk_control']
    assert good['v_score'] > 220


def test_dynamic_required_time_changes_with_advantage_and_confidence():
    fast=league.dynamic_required_days(50,.95,10)
    medium=league.dynamic_required_days(15,.70,3)
    slow=league.dynamic_required_days(3,.30,.2)
    assert 2 <= fast < medium < slow <= 30


def test_dynamic_gate_does_not_promote_on_money_alone():
    required=league.dynamic_required_days(-10,.95,20)
    gate=league.promotion_candidate(99,-2,-3,v_gap=-10,confidence=.95,equity_gap_pct=20,common_days=required)
    assert gate['eligible'] is False
    assert gate['quality_ok'] is False


def test_gauge_geometry_spans_left_to_right_and_ui_is_clickable():
    low=ui.gauge_geometry(0,150,76);mid=ui.gauge_geometry(200,150,76);high=ui.gauge_geometry(400,150,76)
    assert low['x'] < mid['x'] < high['x']
    source=Path('radar_simulation_desktop_v3.py').read_text(encoding='utf-8')
    assert "cursor='hand2'" in source
    assert '_toggle_v_detail' in source
    assert 'v_components' in source
    assert 'eta_text' in source
    assert 'readiness' in source
    assert 'base.GREEN' in source and 'base.RED' in source and 'base.CYAN' in source
    assert ui.REAL_TRADING is False


def test_edge_dynamic_policy_has_no_fixed_ten_day_eligibility():
    edge=Path('supabase/functions/radar-simulator-league/index.ts').read_text(encoding='utf-8')
    assert 'dynamicRequiredDays' in edge
    assert 'promotion_threshold' in edge
    assert 'min_promotion_confidence' in edge
    assert 'min_v_advantage' in edge
    assert 'velocity_per_day' in edge
    assert 'eta_days_low' in edge and 'eta_days_high' in edge
    assert 'readiness>=threshold' in edge
    assert 'streak>=10' not in edge
    assert 'automatic_model_promotion:false' in edge
    assert 'live_execution_allowed:false' in edge
    assert 'real_trading:false' in edge


def test_vscore_history_schema_is_private_and_bounded():
    migration=Path('supabase/migrations/20260911023000_simulator_vscore_dynamic_promotion.sql').read_text(encoding='utf-8').lower()
    assert 'add column if not exists v_score integer' in migration
    assert 'v_score >= 0 and v_score <= 400' in migration
    assert 'promotion_readiness >= 0 and promotion_readiness <= 100' in migration
    assert "promotion_policy text not null default 'dynamic_v1'" in migration


def test_windows_build_uses_vscore_cockpit_entrypoint():
    build=Path('build_windows.ps1').read_text(encoding='utf-8')
    assert '--name RadarSimulationLab radar_simulation_desktop_v3.py' in build
