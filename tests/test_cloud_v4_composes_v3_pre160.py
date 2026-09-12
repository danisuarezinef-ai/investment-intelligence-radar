from pathlib import Path
import cloud_service_v4 as v4
import cloud_service_v5 as v5


def test_production_start_targets_v5_over_v4():
    start=Path('start.sh').read_text(encoding='utf-8')
    text=Path('cloud_service_v5.py').read_text(encoding='utf-8')
    assert 'cloud_service_v5.py' in start
    assert 'import cloud_service_v4 as base4' in text
    assert 'base4.start_v3_runtime()' in text
    assert v5.REAL_TRADING is False


def test_v4_composes_over_v3_not_legacy_cloud_service():
    text=Path('cloud_service_v4.py').read_text(encoding='utf-8')
    assert 'import cloud_service_v3 as base3' in text
    assert 'import cloud_service as base' not in text
    assert 'base3._authority_sync_loop' in text
    assert 'base3.autonomous_simulator_loop' in text
    assert 'closed_loop_runtime_loop' in text
    assert v4.REAL_TRADING is False


def test_v4_runtime_start_is_guarded_idempotently():
    text=Path('cloud_service_v4.py').read_text(encoding='utf-8')
    assert '_V4_RUNTIME_STARTED=False' in text
    assert 'if _V4_RUNTIME_STARTED:' in text
    assert 'runtime.run_worker.main()' in text


def test_v5_is_observability_only_and_preserves_fail_closed_flags():
    text=Path('cloud_service_v5.py').read_text(encoding='utf-8')
    assert '/supabase-health-v1' in text
    assert '/pre160-readiness-board-v1' in text
    assert '/decision-provenance-v1' in text
    assert "'setup_allowed': False" in text
    assert "'can_trade': False" in text
    assert "'real_trading': False" in text
