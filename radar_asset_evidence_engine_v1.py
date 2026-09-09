"""Per-asset evidence aggregation with completeness, conflict and freshness labels."""
from __future__ import annotations
from datetime import datetime, timezone

REAL_TRADING = False

REQUIRED = ('market', 'fundamentals', 'risk')


def _dt(x):
    if not x: return None
    try:
        d = datetime.fromisoformat(str(x).replace('Z', '+00:00'))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def build_asset_evidence(symbol, evidence, now=None, freshness_hours=None):
    now = now or datetime.now(timezone.utc)
    freshness_hours = dict({'market': 24, 'fundamentals': 24*120, 'news': 72, 'risk': 72, 'regime': 24}, **(freshness_hours or {}))
    evidence = evidence or {}
    sections = {}; blockers = []; conflicts = []
    for name in ('market','fundamentals','news','risk','regime'):
        item = evidence.get(name)
        if item is None:
            if name in REQUIRED: blockers.append(f'{name}_missing')
            sections[name] = {'status': 'MISSING'}; continue
        if not isinstance(item, dict):
            blockers.append(f'{name}_invalid'); sections[name] = {'status': 'INVALID'}; continue
        ts = _dt(item.get('known_at') or item.get('timestamp'))
        age_h = None if ts is None else max(0.0, (now - ts).total_seconds()/3600.0)
        stale = ts is None or age_h > float(freshness_hours[name])
        if stale and name in REQUIRED: blockers.append(f'{name}_stale')
        sections[name] = {'status': 'STALE' if stale else 'FRESH', 'age_hours': age_h, 'known_at': ts.isoformat() if ts else None,
                          'source': item.get('source'), 'payload': item.get('payload', item)}

    pos = evidence.get('positive_signals') or []
    neg = evidence.get('negative_signals') or []
    overlap = sorted(set(map(str,pos)) & set(map(str,neg)))
    if overlap: conflicts.append({'type':'same_signal_opposite_direction','signals':overlap})
    complete = not blockers
    return {
        'symbol': str(symbol or '').upper(),
        'evidence_complete': complete,
        'status': 'COMPLETE' if complete and not conflicts else ('CONFLICTED' if complete else 'INCOMPLETE'),
        'sections': sections,
        'blockers': sorted(set(blockers)),
        'conflicts': conflicts,
        'positive_signals': list(pos),
        'negative_signals': list(neg),
        'can_trade': False,
        'real_trading': False,
    }
