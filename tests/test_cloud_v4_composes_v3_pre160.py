from pathlib import Path
import cloud_service_v4 as v4


def test_production_start_still_targets_v4():
    assert 'cloud_service_v4.py' in Path('start.sh').read_text(encoding='utf-8')


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
