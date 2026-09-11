from pathlib import Path

import radar_pre160_persistence_v1 as persist
import radar_strategy_archive_v1 as archive
import radar_release_freeze_v1 as freeze


def test_decision_fingerprint_is_stable_and_competitor_specific():
    row={'symbol':'X','entry_ts':'2026-01-01','exit_ts':'2026-01-02','qty':1,'entry_price':10,'exit_price':11,'entry_capital':10}
    assert persist._fingerprint('a',row)==persist._fingerprint('a',dict(row))
    assert persist._fingerprint('a',row)!=persist._fingerprint('b',row)


def test_migration_is_private_and_forward_boundary_is_explicit():
    sql=Path('supabase/migrations/20260911210000_pre160_strategy_evaluation.sql').read_text(encoding='utf-8').lower()
    assert 'radar_strategy_decision_outcomes' in sql
    assert 'capture_started_at' in sql
    assert 'forward_eligible boolean not null default false' in sql
    assert 'enable row level security' in sql
    assert 'revoke all' in sql and 'from anon, authenticated' in sql
    assert 'check (real_trading = false)' in sql


def test_edge_never_backfills_preexisting_decisions_as_prospective():
    source=Path('supabase/functions/radar-pre160-evaluation/index.ts').read_text(encoding='utf-8')
    assert 'PROSPECTIVE_PAPER_CLOSE' in source
    assert 'DERIVED_PREEXISTING' in source
    assert 'forward_eligible:eligible' in source
    assert 'capture_started_at' in source
    assert 'real_trading:false' in source


def test_archive_policy_never_promotes_models_or_trades():
    hall=archive.hall_candidate({'competitor_key':'a','v_score':300,'v_components':{'evidence':90}},'good')
    event=archive.champion_lineage_event({'competitor_key':'old'},{'competitor_key':'new'},'quality',{})
    assert hall['eligible'] is True
    assert hall['real_trading'] is False
    assert event['automatic_model_promotion'] is False
    assert event['can_trade'] is False


def test_freeze_gate_blocks_setup_until_everything_is_verified():
    states={str(i):'IMPLEMENTED' for i in range(1,71)}
    blocked=freeze.freeze_gate(states,{'status':'RELEASE_READY'},observed_runtime_days=5,required_runtime_days=30)
    assert blocked['setup_allowed'] is False
    assert 'RUNTIME_EVIDENCE' in blocked['blockers']
    ready=freeze.freeze_gate(states,{'status':'RELEASE_READY'},observed_runtime_days=30,required_runtime_days=30)
    assert ready['setup_allowed'] is True
    assert ready['candidate_version']=='1.6.0'
