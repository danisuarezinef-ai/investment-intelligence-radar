"""Portfolio Risk Engine v2.

Adds portfolio-level concentration, correlation, liquidity, FX and drawdown
controls on top of conservative sizing. Missing material risk evidence is handled
fail-closed for new capital. No real trading capability is present.
"""
from __future__ import annotations

REAL_TRADING = False

DEFAULT_LIMITS = {
    'max_position': 0.20,
    'max_invested': 0.70,
    'max_positions': 5,
    'max_sector': 0.35,
    'max_geography': 0.50,
    'max_fx': 0.45,
    'max_pair_correlation': 0.85,
    'min_liquidity_score': 0.50,
    'max_drawdown_pct': -12.0,
    'soft_drawdown_pct': -7.0,
    'min_confidence': 0.42,
}


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _clamp(x, lo=0.0, hi=1.0):
    return max(lo, min(hi, float(x)))


def _positions(portfolio):
    return list((portfolio or {}).get('positions') or [])


def _exposure_by(positions, key, total):
    out = {}
    if not total or total <= 0:
        return out
    for p in positions:
        label = p.get(key)
        value = _f(p.get('value'))
        if label is None or value is None:
            continue
        out[str(label)] = out.get(str(label), 0.0) + value / total
    return out


def risk_gate_v2(portfolio, proposal, metadata=None, correlations=None, limits=None):
    """Gate one proposed new allocation against aggregate portfolio constraints."""
    l = dict(DEFAULT_LIMITS)
    l.update(limits or {})
    portfolio = portfolio or {}
    proposal = proposal or {}
    metadata = metadata or {}
    correlations = correlations or {}

    total = _f(portfolio.get('total'))
    invested = _f(portfolio.get('invested'))
    cash = _f(portfolio.get('cash'))
    drawdown = _f(portfolio.get('max_drawdown_pct'))
    requested = _f(proposal.get('requested_budget'))
    confidence = _f(proposal.get('confidence'))
    symbol = str(proposal.get('symbol') or '')
    positions = _positions(portfolio)
    blockers = []
    warnings = []

    if None in (total, invested, cash, requested, confidence) or total is None or total <= 0:
        blockers.append('capital_or_proposal_incomplete')
    if proposal.get('action') != 'BUY':
        blockers.append('action_not_buy')
    if confidence is not None and confidence < float(l['min_confidence']):
        blockers.append('confidence_below_floor')
    if drawdown is None:
        blockers.append('drawdown_evidence_missing')
    elif drawdown <= float(l['max_drawdown_pct']):
        blockers.append('drawdown_hard_stop')
    if len(positions) >= int(l['max_positions']) and symbol not in {str(p.get('symbol')) for p in positions}:
        blockers.append('position_limit')

    sector = metadata.get('sector')
    geography = metadata.get('geography')
    fx = metadata.get('fx')
    liquidity = _f(metadata.get('liquidity_score'))
    if sector is None:
        blockers.append('sector_evidence_missing')
    if geography is None:
        blockers.append('geography_evidence_missing')
    if fx is None:
        blockers.append('fx_evidence_missing')
    if liquidity is None:
        blockers.append('liquidity_evidence_missing')
    elif liquidity < float(l['min_liquidity_score']):
        blockers.append('liquidity_below_floor')

    allowed = 0.0
    if total is not None and invested is not None and cash is not None and requested is not None and total > 0:
        allowed = min(
            max(0.0, requested),
            max(0.0, total * float(l['max_position'])),
            max(0.0, total * float(l['max_invested']) - invested),
            max(0.0, cash),
        )

        sector_exp = _exposure_by(positions, 'sector', total)
        geo_exp = _exposure_by(positions, 'geography', total)
        fx_exp = _exposure_by(positions, 'fx', total)
        proposed_fraction = allowed / total if total else 0.0
        if sector is not None and sector_exp.get(str(sector), 0.0) + proposed_fraction > float(l['max_sector']):
            blockers.append('sector_concentration')
        if geography is not None and geo_exp.get(str(geography), 0.0) + proposed_fraction > float(l['max_geography']):
            blockers.append('geography_concentration')
        if fx is not None and str(fx).upper() not in ('EUR', 'BASE', 'NONE') and fx_exp.get(str(fx), 0.0) + proposed_fraction > float(l['max_fx']):
            blockers.append('fx_concentration')

    held_symbols = [str(p.get('symbol') or '') for p in positions if p.get('symbol')]
    missing_corr = []
    high_corr = []
    for held in held_symbols:
        if held == symbol:
            continue
        key1 = (symbol, held)
        key2 = (held, symbol)
        raw = correlations.get(key1, correlations.get(key2))
        corr = _f(raw)
        if corr is None:
            missing_corr.append(held)
        elif corr > float(l['max_pair_correlation']):
            high_corr.append({'symbol': held, 'correlation': corr})
    if missing_corr:
        blockers.append('correlation_evidence_missing')
    if high_corr:
        blockers.append('pair_correlation_limit')

    risk_multiplier = 1.0
    if drawdown is not None and drawdown <= float(l['soft_drawdown_pct']):
        risk_multiplier *= 0.5
        warnings.append('soft_drawdown_reduction')
    if liquidity is not None:
        risk_multiplier *= _clamp(liquidity)
    allowed *= risk_multiplier
    if blockers:
        allowed = 0.0

    return {
        'symbol': symbol,
        'blocked': allowed <= 0,
        'allowed_budget': max(0.0, allowed),
        'risk_multiplier': risk_multiplier,
        'blockers': sorted(set(blockers)),
        'warnings': warnings,
        'high_correlations': high_corr,
        'missing_correlations': missing_corr,
        'limits': l,
        'can_trade': False,
        'real_trading': False,
    }


def portfolio_risk_summary(portfolio, limits=None):
    l = dict(DEFAULT_LIMITS)
    l.update(limits or {})
    total = _f((portfolio or {}).get('total'))
    positions = _positions(portfolio)
    return {
        'sector_exposure': _exposure_by(positions, 'sector', total),
        'geography_exposure': _exposure_by(positions, 'geography', total),
        'fx_exposure': _exposure_by(positions, 'fx', total),
        'position_count': len(positions),
        'limits': l,
        'can_trade': False,
        'real_trading': False,
    }
