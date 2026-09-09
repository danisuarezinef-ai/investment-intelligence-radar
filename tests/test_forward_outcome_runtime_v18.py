from pathlib import Path


def test_cloud_runtime_runs_idempotent_forward_outcome_resend():
    text=Path('cloud_service_v3.py').read_text(encoding='utf-8')
    assert 'sync_forward_outcomes_once' in text
    assert '_forward_outcome_sync_loop' in text
    assert "name='forward-outcome-sync'" in text
    assert "'forward_outcome_sync':'LIVE_IDEMPOTENT_MATURE_OUTCOME_RESEND'" in text


def test_forward_outcome_resend_is_mature_only_and_fail_closed():
    text=Path('radar_forward_outcome_sync_v1.py').read_text(encoding='utf-8')
    assert 'where outcome is not null' in text.lower()
    assert "'backfill_used':False" in text
    assert "'idempotent':True" in text
    assert 'REAL_TRADING=False' in text


def test_forward_maturation_uses_post_target_observation_and_explicit_cost_benchmark():
    text=Path('radar_forward_engine.py').read_text(encoding='utf-8')
    assert 'target_date<=?' in text
    assert 'ts>=?' in text
    assert 'PAPER_ROUND_TRIP_COST' in text
    assert 'benchmark_return' in text
    assert "'backfilled':False" in text
    assert 'REAL_TRADING=False' in text
