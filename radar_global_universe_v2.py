"""Global Opportunity Universe v2.

Progressive universe triage: cheap metadata screening first, deeper evidence only for
surviving candidates. The module does not fetch external data and does not execute trades.
"""
from __future__ import annotations

REAL_TRADING = False

DEFAULT_POLICY = {
    'min_liquidity_score': 0.45,
    'max_candidates_for_deep_review': 100,
    'max_candidates_for_decision_lab': 30,
}


def _f(x):
    try: return float(x)
    except (TypeError, ValueError): return None


def universe_triage(candidates, policy=None):
    p = dict(DEFAULT_POLICY); p.update(policy or {})
    accepted = []; rejected = []
    for c in candidates or []:
        if not isinstance(c, dict):
            rejected.append({'symbol': None, 'reason': 'invalid_candidate'}); continue
        symbol = str(c.get('symbol') or '').strip().upper()
        liq = _f(c.get('liquidity_score'))
        region = c.get('geography') or c.get('region')
        currency = c.get('fx') or c.get('currency')
        tradable = c.get('tradable')
        blockers = []
        if not symbol: blockers.append('symbol_missing')
        if tradable is not True: blockers.append('tradability_not_verified')
        if liq is None: blockers.append('liquidity_missing')
        elif liq < float(p['min_liquidity_score']): blockers.append('liquidity_below_floor')
        if region is None: blockers.append('geography_missing')
        if currency is None: blockers.append('currency_missing')
        if blockers:
            rejected.append({'symbol': symbol or None, 'reason': sorted(set(blockers))}); continue
        cheap_score = liq
        if c.get('primary_listing') is True: cheap_score += 0.10
        if c.get('price_fresh') is True: cheap_score += 0.15
        accepted.append({**c, 'symbol': symbol, 'cheap_screen_score': cheap_score})

    accepted.sort(key=lambda x: x['cheap_screen_score'], reverse=True)
    deep = accepted[:int(p['max_candidates_for_deep_review'])]
    decision = deep[:int(p['max_candidates_for_decision_lab'])]
    return {
        'input_count': len(candidates or []),
        'accepted_count': len(accepted),
        'rejected_count': len(rejected),
        'deep_review_symbols': [x['symbol'] for x in deep],
        'decision_lab_symbols': [x['symbol'] for x in decision],
        'rejected': rejected,
        'policy': p,
        'policy_note': 'progressive screening policy; NOT empirically validated as optimal',
        'can_trade': False,
        'real_trading': False,
    }
