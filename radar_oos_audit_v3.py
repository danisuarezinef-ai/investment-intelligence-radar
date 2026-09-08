"""Strict forward / out-of-sample audit v3.

Extends per-fold checks with cross-fold chronological consistency and explicit
forward-evidence requirements. It is read-only and cannot enable trading.
"""
from __future__ import annotations
from datetime import datetime

REAL_TRADING = False


def _dt(x):
    if not x:
        return None
    try:
        return datetime.fromisoformat(str(x).replace('Z', '+00:00'))
    except Exception:
        return None


def strict_walk_forward_audit(folds, min_folds=4):
    rows = []
    violations = []
    previous_validation_start = None
    previous_validation_end = None
    for idx, fold in enumerate(folds or [], 1):
        ts = _dt(fold.get('train_start'))
        te = _dt(fold.get('train_end'))
        vs = _dt(fold.get('validation_start'))
        ve = _dt(fold.get('validation_end'))
        internal_order = bool(ts and te and vs and ve and ts <= te < vs <= ve)
        counts = bool(
            isinstance(fold.get('observations_train'), int) and fold.get('observations_train') > 0
            and isinstance(fold.get('observations_validation'), int) and fold.get('observations_validation') > 0
        )
        holdout = fold.get('holdout') is True
        no_lookahead = fold.get('lookahead') is False
        frozen_features = fold.get('features_frozen_at_train_end') is True
        pit_membership = fold.get('pit_membership') is True

        chronological_fold_order = True
        non_overlapping_validation = True
        if previous_validation_start is not None and vs is not None:
            chronological_fold_order = vs > previous_validation_start
        if previous_validation_end is not None and vs is not None:
            non_overlapping_validation = vs > previous_validation_end

        ok = all((internal_order, counts, holdout, no_lookahead,
                  frozen_features, pit_membership,
                  chronological_fold_order, non_overlapping_validation))
        check = {
            'fold': idx,
            'internal_temporal_order': internal_order,
            'positive_counts': counts,
            'holdout': holdout,
            'lookahead_false': no_lookahead,
            'features_frozen_at_train_end': frozen_features,
            'pit_membership': pit_membership,
            'chronological_fold_order': chronological_fold_order,
            'non_overlapping_validation': non_overlapping_validation,
            'ok': ok,
        }
        rows.append(check)
        if not ok:
            violations.append(idx)
        if vs is not None:
            previous_validation_start = vs
        if ve is not None:
            previous_validation_end = ve

    sufficient = len(rows) >= int(min_folds)
    return {
        'folds': len(rows),
        'minimum_folds': int(min_folds),
        'sufficient_folds': sufficient,
        'violations': violations,
        'pass': sufficient and not violations,
        'checks': rows,
        'can_trade': False,
        'real_trading': False,
    }


def forward_integrity_audit(records, started_at=None):
    boundary = _dt(started_at)
    failures = []
    valid = 0
    fully_attributable = 0
    for idx, row in enumerate(records or []):
        created = _dt(row.get('created_at'))
        evaluated = _dt(row.get('evaluated_at'))
        immutable = row.get('immutable') is True
        after_boundary = bool(boundary and created and created >= boundary)
        matured_after_creation = bool(created and evaluated and evaluated >= created)
        no_backfill = row.get('backfilled') is False
        pit = row.get('pit_verified') is True
        benchmark = row.get('benchmark_available') is True
        costs = row.get('costs_included') is True
        outcome = row.get('return_pct') is not None
        ok = all((immutable, after_boundary, matured_after_creation, no_backfill, pit, outcome))
        if ok:
            valid += 1
        else:
            failures.append({
                'index': idx, 'immutable': immutable,
                'after_boundary': after_boundary,
                'matured_after_creation': matured_after_creation,
                'no_backfill': no_backfill, 'pit_verified': pit,
                'has_outcome': outcome,
            })
        if ok and benchmark and costs:
            fully_attributable += 1
    return {
        'records': len(list(records or [])),
        'valid_forward_records': valid,
        'fully_attributable_records': fully_attributable,
        'failures': failures,
        'boundary_verified': boundary is not None,
        'all_forward_valid': boundary is not None and not failures and valid > 0,
        'all_attributable': valid > 0 and fully_attributable == valid,
        'can_trade': False,
        'real_trading': False,
    }
