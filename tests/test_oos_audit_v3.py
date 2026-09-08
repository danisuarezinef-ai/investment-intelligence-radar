from radar_oos_audit_v3 import strict_walk_forward_audit, forward_integrity_audit


def fold(train_start, train_end, validation_start, validation_end):
    return {
        'train_start': train_start,
        'train_end': train_end,
        'validation_start': validation_start,
        'validation_end': validation_end,
        'observations_train': 100,
        'observations_validation': 20,
        'holdout': True,
        'lookahead': False,
        'features_frozen_at_train_end': True,
        'pit_membership': True,
    }


def test_strict_walk_forward_passes_clean_non_overlapping_sequence():
    folds = [
        fold('2025-01-01','2025-03-31','2025-04-01','2025-04-30'),
        fold('2025-01-01','2025-04-30','2025-05-01','2025-05-31'),
        fold('2025-01-01','2025-05-31','2025-06-01','2025-06-30'),
        fold('2025-01-01','2025-06-30','2025-07-01','2025-07-31'),
    ]
    out = strict_walk_forward_audit(folds)
    assert out['pass'] is True
    assert out['violations'] == []
    assert out['real_trading'] is False


def test_strict_walk_forward_rejects_validation_overlap():
    folds = [
        fold('2025-01-01','2025-03-31','2025-04-01','2025-04-30'),
        fold('2025-01-01','2025-04-10','2025-04-20','2025-05-20'),
        fold('2025-01-01','2025-05-31','2025-06-01','2025-06-30'),
        fold('2025-01-01','2025-06-30','2025-07-01','2025-07-31'),
    ]
    out = strict_walk_forward_audit(folds)
    assert out['pass'] is False
    assert 2 in out['violations']
    assert out['checks'][1]['non_overlapping_validation'] is False


def test_forward_integrity_requires_boundary_immutability_and_no_backfill():
    records = [{
        'created_at': '2026-09-09T00:10:00+00:00',
        'evaluated_at': '2026-09-10T00:10:00+00:00',
        'immutable': True,
        'backfilled': False,
        'pit_verified': True,
        'return_pct': 2.0,
        'benchmark_available': True,
        'costs_included': True,
    }]
    out = forward_integrity_audit(records, '2026-09-09T00:00:00+00:00')
    assert out['all_forward_valid'] is True
    assert out['all_attributable'] is True


def test_forward_integrity_rejects_backfill():
    records = [{
        'created_at': '2026-09-09T00:10:00+00:00',
        'evaluated_at': '2026-09-10T00:10:00+00:00',
        'immutable': True,
        'backfilled': True,
        'pit_verified': True,
        'return_pct': 2.0,
        'benchmark_available': True,
        'costs_included': True,
    }]
    out = forward_integrity_audit(records, '2026-09-09T00:00:00+00:00')
    assert out['all_forward_valid'] is False
    assert out['failures'][0]['no_backfill'] is False
