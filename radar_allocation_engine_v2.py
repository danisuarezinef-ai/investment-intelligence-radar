"""Allocation Engine v2: global capital competition including cash and existing positions."""
from __future__ import annotations

REAL_TRADING = False

DEFAULT_POLICY = {
    'max_invested': 0.75,
    'max_position': 0.18,
    'max_positions': 8,
    'cash_floor': 0.15,
    'min_confidence': 0.45,
    'min_net_utility': 0.0,
}


def _f(x):
    try: return float(x)
    except (TypeError, ValueError): return None


def _score(card):
    if not isinstance(card, dict) or card.get('evidence_complete') is not True:
        return None
    er = _f(card.get('expected_return_pct')); down = _f(card.get('downside_pct'))
    conf = _f(card.get('confidence')); risk = _f(card.get('risk_score', card.get('valuation_risk')))
    if None in (er, down, conf, risk): return None
    if conf < 0 or conf > 1: return None
    return (er - max(0.0, -down) - max(0.0, risk)) * conf


def allocate_capital_v2(cards, portfolio, risk_results=None, policy=None):
    p = dict(DEFAULT_POLICY); p.update(policy or {})
    portfolio = portfolio or {}; risk_results = risk_results or {}
    total = _f(portfolio.get('total')); cash = _f(portfolio.get('cash')); invested = _f(portfolio.get('invested'))
    if None in (total, cash, invested) or total is None or total <= 0 or cash < 0 or invested < 0:
        return {'blocked': True, 'blockers': ['capital_state_incomplete'], 'allocations': [], 'cash_target': None,
                'can_trade': False, 'real_trading': False}

    cash_floor_value = total * float(p['cash_floor'])
    max_invested_value = total * float(p['max_invested'])
    deployable = max(0.0, min(cash - cash_floor_value, max_invested_value - invested))
    competitors = []
    for card in cards or []:
        symbol = str(card.get('symbol') or '') if isinstance(card, dict) else ''
        score = _score(card)
        if not symbol or score is None or score <= float(p['min_net_utility']): continue
        conf = _f(card.get('confidence'))
        if conf is None or conf < float(p['min_confidence']): continue
        rr = risk_results.get(symbol) or {}
        if rr and rr.get('blocked'): continue
        risk_mult = _f(rr.get('risk_multiplier')) if rr else 1.0
        if risk_mult is None: continue
        adjusted = score * max(0.0, min(1.0, risk_mult))
        if adjusted <= 0: continue
        competitors.append((card, adjusted, rr))

    competitors.sort(key=lambda x: x[1], reverse=True)
    competitors = competitors[:int(p['max_positions'])]
    total_score = sum(x[1] for x in competitors)
    allocations = []
    remaining = deployable
    cap = total * float(p['max_position'])
    for card, adjusted, rr in competitors:
        raw = deployable * adjusted / total_score if total_score > 0 else 0.0
        risk_cap = _f(rr.get('allowed_budget')) if rr else None
        budget = min(raw, cap, remaining)
        if risk_cap is not None: budget = min(budget, risk_cap)
        if budget <= 0: continue
        allocations.append({'symbol': card.get('symbol'), 'action': card.get('action'), 'target_budget': budget,
                            'target_fraction': budget / total, 'capital_competition_score': adjusted,
                            'confidence': _f(card.get('confidence')), 'horizon': card.get('horizon'),
                            'real_trading': False})
        remaining -= budget

    return {
        'blocked': False if allocations or deployable == 0 else True,
        'blockers': [] if allocations or deployable == 0 else ['no_eligible_opportunities'],
        'allocations': allocations,
        'deployable_budget': deployable,
        'allocated_budget': sum(a['target_budget'] for a in allocations),
        'cash_target': max(cash_floor_value, cash - sum(a['target_budget'] for a in allocations)),
        'cash_is_competitor': True,
        'policy_note': 'capital competition heuristic; NOT empirically validated as optimal',
        'can_trade': False,
        'real_trading': False,
    }
