"""Canonical prospective evidence authority for pre-1.6 tasks 326-340.

This module only reads immutable PAPER/forward evidence already created by the runtime.
It never backfills predictions, creates trades, reconstructs envelopes, or authorizes
promotion/release.  Missing metadata remains explicit and lowers evidence quality.
"""
from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any

from radar_core import con
from radar_investment_memory import init_memory

REAL_TRADING = False
HORIZONS = ('1d', '1w', '1m', '3m')
HORIZON_MIN_N = {'1d': 40, '1w': 30, '1m': 25, '3m': 20}
HORIZON_MIN_DAYS = {'1d': 3, '1w': 7, '1m': 21, '3m': 63}


def _json(value: Any, default=None):
    if isinstance(value, (dict, list)):
        return value
    if value in (None, ''):
        return {} if default is None else default
    try:
        return json.loads(value)
    except Exception:
        return {} if default is None else default


def _dt(value):
    if value in (None, ''):
        return None
    try:
        d = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return d.astimezone(timezone.utc)
    except Exception:
        return None


def _table_exists(db, name: str) -> bool:
    try:
        return bool(db.execute("select 1 from sqlite_master where type='table' and name=?", (name,)).fetchone())
    except Exception:
        return False


def _quality(row: dict) -> tuple[float, dict]:
    outcome = row.get('outcome') or {}
    provenance = row.get('provenance') or {}
    created = _dt(row.get('created_at'))
    cutoff = _dt(row.get('data_cutoff'))
    known = _dt(row.get('known_at_boundary'))
    pit = bool(created and cutoff and known and cutoff <= created and known <= created and provenance.get('lookahead') is False)
    natural = outcome.get('backfilled') is False if outcome else True
    immutable = bool(row.get('prediction_hash') and row.get('feature_fingerprint') and row.get('thesis_fingerprint'))
    benchmark = bool(outcome and outcome.get('benchmark_return') is not None and outcome.get('benchmark_evidence'))
    cost = bool(outcome and outcome.get('cost') is not None and outcome.get('cost_model'))
    checks = {'pit_valid': pit, 'natural': natural, 'immutable_identity': immutable,
              'benchmark_complete': benchmark, 'cost_complete': cost}
    # Mature rows require all five checks for full quality; open rows can still have a
    # prospective quality score without pretending benchmark/cost outcome evidence exists.
    weights = {'pit_valid': .30, 'natural': .20, 'immutable_identity': .25,
               'benchmark_complete': .15, 'cost_complete': .10}
    score = sum(weights[k] for k, ok in checks.items() if ok)
    return round(score, 6), checks


def _direction_hit(decision: str, raw_return):
    if not isinstance(raw_return, (int, float)):
        return None
    d = str(decision or '').upper()
    if d == 'BUY':
        return bool(raw_return > 0)
    if d == 'SELL':
        return bool(raw_return < 0)
    return None


def canonical_forward_rows(db=None) -> list[dict]:
    own = db is None
    db = db or con()
    init_memory(db)
    cols = ('id,origin_node,origin_id,created_at,target_date,asset,horizon,model_version,'
            'prediction_hash,feature_fingerprint,thesis_fingerprint,confidence,uncertainty,'
            'decision_state,paper_allocation,data_cutoff,known_at_boundary,provenance_snapshot,'
            'payload,outcome,evaluated_at')
    raw = db.execute(f'select {cols} from prediction_ledger order by created_at,id').fetchall()
    rows = []
    for r in raw:
        uncertainty = _json(r[12])
        allocation = _json(r[14], None) if r[14] is not None else None
        provenance = _json(r[17])
        payload = _json(r[18])
        outcome = _json(r[19], None) if r[19] is not None else None
        created = _dt(r[3])
        evaluated = _dt(r[20])
        decision = str(r[13] or 'WAIT').upper()
        raw_return = outcome.get('return') if isinstance(outcome, dict) else None
        regime = uncertainty.get('regime') or payload.get('regime') or (payload.get('uncertainty') or {}).get('regime')
        sector = payload.get('sector') or (payload.get('metadata') or {}).get('sector')
        market = payload.get('market') or (payload.get('metadata') or {}).get('market')
        family = payload.get('family') or payload.get('strategy_family') or str(r[7] or '')
        row = {
            'prediction_id': r[0], 'origin_node': r[1], 'origin_id': r[2],
            'created_at': r[3], 'target_date': r[4], 'symbol': r[5], 'horizon': r[6],
            'model_version': r[7], 'prediction_hash': r[8], 'feature_fingerprint': r[9],
            'thesis_fingerprint': r[10], 'confidence': float(r[11] or 0),
            'uncertainty': uncertainty, 'decision_state': decision, 'paper_allocation': allocation,
            'data_cutoff': r[15], 'known_at_boundary': r[16], 'provenance': provenance,
            'payload': payload, 'outcome': outcome, 'evaluated_at': r[20],
            'matured': outcome is not None and evaluated is not None,
            'natural': not (isinstance(outcome, dict) and outcome.get('backfilled') is True),
            'regime': regime, 'sector': sector, 'market': market, 'family': family,
            'period': created.date().isoformat() if created else None,
            'raw_return': raw_return,
            'net_return': outcome.get('net_return') if isinstance(outcome, dict) else None,
            'excess_return': outcome.get('excess_return') if isinstance(outcome, dict) else None,
            'benchmark_return': outcome.get('benchmark_return') if isinstance(outcome, dict) else None,
            'cost': outcome.get('cost') if isinstance(outcome, dict) else None,
            'action_hit': _direction_hit(decision, raw_return),
            'evidence_key': r[8],
        }
        q, checks = _quality(row)
        row['quality'] = q
        row['quality_checks'] = checks
        # A cohort is intentionally broader than one asset: simultaneous predictions
        # share market information and must not be treated as fully independent.
        cohort_time = created.replace(minute=0, second=0, microsecond=0).isoformat() if created else 'UNKNOWN'
        row['independence_cluster'] = '|'.join((cohort_time, str(row['horizon']), str(row['model_version']), str(regime or 'UNKNOWN')))
        rows.append(row)
    if own:
        db.close()
    return rows


def deduplicate(rows: list[dict]) -> dict:
    seen = {}
    duplicates = []
    collisions = []
    for r in rows or []:
        key = str(r.get('evidence_key') or r.get('prediction_hash') or '')
        if not key:
            collisions.append({'reason': 'MISSING_EVIDENCE_KEY', 'prediction_id': r.get('prediction_id')})
            continue
        if key in seen:
            duplicates.append(key)
            # Same immutable hash with materially different core fields is corruption,
            # not merely a duplicate observation.
            core = ('symbol', 'horizon', 'model_version', 'created_at')
            if any(seen[key].get(k) != r.get(k) for k in core):
                collisions.append({'reason': 'HASH_COLLISION_OR_MUTATION', 'evidence_key': key})
            continue
        seen[key] = r
    return {'rows': list(seen.values()), 'input_n': len(rows or []), 'unique_n': len(seen),
            'duplicates': duplicates, 'collisions': collisions,
            'double_count_prevented': bool(duplicates) or len(seen) == len(rows or []),
            'real_trading': False}


def effective_sample_size_v2(rows: list[dict]) -> dict:
    matured = [r for r in rows or [] if r.get('matured') is True and r.get('natural') is True]
    if not matured:
        return {'n': 0, 'quality_ess': 0.0, 'cluster_ess': 0.0, 'conservative_ess': 0.0,
                'clusters': 0, 'real_trading': False}
    weights = [max(0.01, min(1.0, float(r.get('quality') or 0))) for r in matured]
    sw = sum(weights); quality_ess = (sw * sw / sum(w*w for w in weights)) if weights else 0.0
    clusters = Counter(str(r.get('independence_cluster') or 'UNKNOWN') for r in matured)
    # Kish ESS on cluster sizes: simultaneous correlated rows contribute closer to
    # independent cohorts than to the raw observation count.
    sizes = list(clusters.values()); total = sum(sizes)
    cluster_ess = (total * total / sum(x*x for x in sizes)) if sizes else 0.0
    conservative = min(quality_ess, cluster_ess)
    return {'n': len(matured), 'quality_ess': round(quality_ess, 4),
            'cluster_ess': round(cluster_ess, 4), 'conservative_ess': round(conservative, 4),
            'clusters': len(clusters), 'largest_cluster': max(sizes) if sizes else 0,
            'real_trading': False}


def horizon_maturity(rows: list[dict]) -> dict:
    out = {}
    for h in HORIZONS:
        xs = [r for r in rows or [] if r.get('horizon') == h and r.get('matured') is True and r.get('natural') is True]
        dates = sorted(x for x in (_dt(r.get('created_at')) for r in xs) if x)
        days = (dates[-1].date() - dates[0].date()).days + 1 if dates else 0
        assets = len({r.get('symbol') for r in xs if r.get('symbol')})
        quality = sum(float(r.get('quality') or 0) for r in xs) / len(xs) if xs else None
        enough_n = len(xs) >= HORIZON_MIN_N[h]
        enough_time = days >= HORIZON_MIN_DAYS[h]
        enough_assets = assets >= 8
        if enough_n and enough_time and enough_assets:
            status = 'PASS'
        elif not enough_time and len(xs):
            status = 'PENDING_TIME'
        else:
            status = 'PENDING_SAMPLE'
        out[h] = {'status': status, 'n': len(xs), 'calendar_days': days, 'assets': assets,
                  'mean_quality': quality, 'min_n': HORIZON_MIN_N[h],
                  'min_days': HORIZON_MIN_DAYS[h], 'min_assets': 8}
    return out


def dimension_maturity(rows: list[dict], key: str, *, min_n=20, min_cells=2) -> dict:
    matured = [r for r in rows or [] if r.get('matured') is True and r.get('natural') is True]
    counts = Counter(str(r.get(key) or 'UNKNOWN') for r in matured)
    known = {k: v for k, v in counts.items() if k != 'UNKNOWN'}
    mature = {k: v for k, v in known.items() if v >= int(min_n)}
    missing_fraction = counts.get('UNKNOWN', 0) / max(1, len(matured))
    status = 'PASS' if len(mature) >= int(min_cells) else 'PENDING_SAMPLE'
    return {'status': status, 'counts': known, 'mature_cells': mature,
            'unknown': counts.get('UNKNOWN', 0), 'missing_fraction': missing_fraction,
            'min_n': min_n, 'min_cells': min_cells, 'real_trading': False}


def asset_independence(rows: list[dict]) -> dict:
    matured = [r for r in rows or [] if r.get('matured') is True and r.get('natural') is True]
    counts = Counter(str(r.get('symbol') or '') for r in matured if r.get('symbol'))
    n = sum(counts.values()); max_share = max(counts.values()) / n if n and counts else None
    status = 'PASS' if len(counts) >= 8 and max_share is not None and max_share <= .25 else 'PENDING_SAMPLE'
    return {'status': status, 'assets': len(counts), 'n': n, 'max_asset_share': max_share,
            'counts': dict(counts), 'real_trading': False}


def decision_envelope_status(db=None) -> dict:
    own = db is None
    db = db or con()
    if not _table_exists(db, 'radar_pre160_decision_envelopes'):
        if own: db.close()
        return {'status': 'PENDING_SAMPLE', 'count': 0, 'natural_envelope': False,
                'provenance_complete': False, 'entry_linked_without_reconstruction': False,
                'prospective_close': False, 'task_150_eligible': False, 'real_trading': False}
    try:
        rows = db.execute('select * from radar_pre160_decision_envelopes order by id desc limit 100').fetchall()
        cols = [x[1] for x in db.execute('pragma table_info(radar_pre160_decision_envelopes)').fetchall()]
        envs = [dict(zip(cols, r)) for r in rows]
    except Exception:
        envs = []
    if own: db.close()
    good = []
    for e in envs:
        if bool(e.get('real_trading')):
            continue
        prov = _json(e.get('provenance'))
        benchmark = _json(e.get('benchmark_snapshot'))
        costs = _json(e.get('cost_snapshot'))
        provider = _json(e.get('provider_snapshot'))
        complete = bool(e.get('source_key') and e.get('trade_ts') and e.get('decision_fingerprint') and
                        e.get('envelope_hash') and benchmark and costs and provider and prov)
        if complete:
            good.append(e)
    # Exact close linkage is intentionally not guessed from exit fields. A future
    # runtime may add an explicit immutable close reference; until then it stays pending.
    prospective = any(_json(e.get('payload')).get('prospective_close_verified') is True for e in good)
    entry_linked = any(_json(e.get('payload')).get('entry_linked_without_reconstruction') is True for e in good)
    return {'status': 'PASS' if good else 'PENDING_SAMPLE', 'count': len(envs),
            'natural_envelope': bool(good), 'provenance_complete': bool(good),
            'entry_linked_without_reconstruction': entry_linked,
            'prospective_close': prospective,
            'task_150_eligible': bool(good and entry_linked and prospective),
            'reconstruction_allowed': False, 'backfill_allowed': False,
            'real_trading': False}


def forward_evidence_snapshot(db=None) -> dict:
    rows = canonical_forward_rows(db)
    dedup = deduplicate(rows)
    unique = dedup['rows']
    matured = [r for r in unique if r.get('matured') is True and r.get('natural') is True]
    quality = [float(r.get('quality') or 0) for r in matured]
    horizons = horizon_maturity(unique)
    regimes = dimension_maturity(unique, 'regime', min_n=20, min_cells=2)
    sectors = dimension_maturity(unique, 'sector', min_n=15, min_cells=3)
    markets = dimension_maturity(unique, 'market', min_n=20, min_cells=2)
    assets = asset_independence(unique)
    ess = effective_sample_size_v2(unique)
    envelope = decision_envelope_status(db)
    return {
        'status': 'CANONICAL_FORWARD_EVIDENCE_V2',
        'rows_total': len(unique), 'rows_matured_natural': len(matured),
        'deduplication': {k:v for k,v in dedup.items() if k != 'rows'},
        'mean_evidence_quality': sum(quality)/len(quality) if quality else None,
        'ess': ess, 'horizons': horizons, 'regimes': regimes, 'sectors': sectors,
        'markets': markets, 'assets': assets, 'decision_envelope': envelope,
        'canonical_key': 'prediction_hash', 'backfill_allowed': False,
        'synthetic_evidence_can_mature': False, 'can_trade': False, 'real_trading': False,
    }
