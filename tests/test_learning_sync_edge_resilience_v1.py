from pathlib import Path


def test_learning_edge_batches_prediction_resolution():
    src=Path('supabase/functions/radar-learning-sync/index.ts').read_text(encoding='utf-8')
    assert 'const WRITE_CONCURRENCY=20;' in src
    assert 'const READ_CHUNK=100;' in src
    assert 'async function mapConcurrent' in src
    assert 'resolvePredictionOutcomes' in src
    assert '.eq("origin_node",job.node).in("origin_id",job.ids)' in src
    assert 'prediction_outcomes' in src


def test_learning_edge_keeps_single_assignment_outcomes():
    src=Path('supabase/functions/radar-learning-sync/index.ts').read_text(encoding='utf-8')
    assert 'applySingleAssignmentOutcomes' in src
    assert '.is("outcome",null)' in src
    assert 'decision_forward_ledger' in src
    assert 'brain_shadow_predictions' in src
    assert 'edge_ms' in src


def test_learning_edge_remains_private_and_no_real_trading_authority():
    src=Path('supabase/functions/radar-learning-sync/index.ts').read_text(encoding='utf-8')
    assert 'x-radar-token' in src.lower()
    assert 'EXPECTED_HASH' in src
    assert 'unauthorized' in src
    assert 'real_trading:false' in src
