"""Portfolio Allocation Engine v1.

Converts comparable Decision Lab v5 cards into a target-capital proposal.
The engine is deliberately fail-closed: only complete BUY evidence can receive
new capital. It never executes trades and never enables real trading.
"""
from __future__ import annotations

REAL_TRADING = False

DEFAULT_POLICY = {
    'max_invested': 0.70,
    'max_position': 0.20,
    'max_positions': 5,
    'min_confidence': 0.42,
    'min_expected_return_pct': 0.0,
}


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _clamp(x, lo=0.0, hi=1.0):
    return max(lo, min(hi, float(x)))


def opportunity_utility(card):
    """Risk-aware comparable utility using only explicit card evidence."""
    if not isinstance(card, dict):
        return None
    if card.get('action') != 'BUY' or card.get('evidence_complete') is not True:
        return None
    er = _f(card.get('expected_return_pct'))
    downside = _f(card.get('downside_pct'))
    confidence = _f(card.get('confidence'))
    valuation = _f(card.get('valuation_risk'))
    if None in (er, downside, confidence, valuation):
        return None
    # Penalize downside magnitude and valuation risk. This is a deterministic
    # allocation heuristic, not an empirically validated optimal objective.
    risk_penalty = max(0.0, -downside) + max(0.0, valuation)
    return (er - risk_penalty) * _clamp(confidence)


def allocate_capital(cards, portfolio, policy=None):
    """Return a target allocation proposal across all eligible opportunities.

    Existing capital state is supplied by the caller. Missing or inconsistent
    capital data blocks new allocation rather than being inferred.
    """
    p = dict(DEFAULT_POLICY)
    p.update(policy or {})
    portfolio = portfolio or {}
    total = _f(portfolio.get('total'))
    invested = _f(portfolio.get('invested'))
    cash = _f(portfolio.get('cash'))
    if total is None or invested is None or cash is None or total <= 0 or invested < 0 or cash < 0:
        return {
            'eligible': [], 'allocations': [], 'blocked': True,
            'blockers': ['capital_state_incomplete'], 'total_budget': 0.0,
            'can_trade': False, 'real_trading': False,
        }

    gross_remaining = max(0.0, total * float(p['max_invested']) - invested)
    available = min(gross_remaining, cash)
    eligible = []
    for card in cards or []:
        conf = _f(card.get('confidence')) if isinstance(card, dict) else None
        er = _f(card.get('expected_return_pct')) if isinstance(card, dict) else None
        util = opportunity_utility(card)
        if util is None or util <= 0:
            continue
        if conf is None or conf < float(p['min_confidence']):
            continue
        if er is None or er <= float(p['min_expected_return_pct']):
            continue
        eligible.append((card, util))

    eligible.sort(key=lambda x: x[1], reverse=True)
    eligible = eligible[:max(0, int(p['max_positions']))]
    if available <= 0 or not eligible:
        return {
            'eligible': [x[0].get('symbol') for x in eligible], 'allocations': [],
            'blocked': True,
            'blockers': ['no_available_budget'] if available <= 0 else ['no_eligible_buy_decisions'],
            'total_budget': 0.0, 'can_trade': False, 'real_trading': False,
        }

    util_sum = sum(u for _, u in eligible)
    allocations = []
    used = 0.0
    per_position_cap = total * float(p['max_position'])
    for card, util in eligible:
        raw = available * (util / util_sum) if util_sum > 0 else 0.0
        budget = min(raw, per_position_cap)
        budget = max(0.0, min(budget, available - used))
        if budget <= 0:
            continue
        allocations.append({
            'symbol': card.get('symbol'),
            'horizon': card.get('horizon'),
            'action': 'BUY',
            'requested_budget': budget,
            'requested_fraction': budget / total,
            'utility': util,
            'confidence': _f(card.get('confidence')),
            'expected_return_pct': _f(card.get('expected_return_pct')),
            'downside_pct': _f(card.get('downside_pct')),
            'real_trading': False,
        })
        used += budget

    return {
        'eligible': [x[0].get('symbol') for x in eligible],
        'allocations': allocations,
        'blocked': not bool(allocations),
        'blockers': [] if allocations else ['allocation_collapsed_to_zero'],
        'total_budget': used,
        'available_budget': available,
        'max_invested': float(p['max_invested']),
        'max_position': float(p['max_position']),
        'policy_note': 'heuristic policy; NOT empirically validated as optimal',
        'can_trade': False,
        'real_trading': False,
    }
