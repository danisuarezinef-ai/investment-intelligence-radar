"""Fail-closed contracts for autonomous PAPER simulator priorities 8-12.

Covers PAPER risk, champion/challenger governance, abstention/disagreement,
accounting reconciliation and forward-only maturity clocks. This module cannot
place broker orders, enable live trading, auto-promote a model, release a build,
or authorize Setup 1.6.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable

REAL_TRADING = False
DEFAULT_RISK_LIMITS = {
    'max_gross_pct': 0.75,
    'max_net_pct': 0.70,
    'max_position_pct': 0.15,
    'max_sector_pct': 0.30,
    'max_correlated_cluster_pct': 0.35,
    'min_cash_pct': 0.20,
    'max_drawdown_pct': 0.10,
    'max_portfolio_volatility': 0.35,
    'max_uncertainty': 0.65,
}


def _utc(value: Any):
    if value in (None, ''):
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    except Exception:
        return None
    if dt.tzinfo is None:
        return None
    return dt.astimezone(timezone.utc)


def _safe_float(value: Any, default=None):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def paper_risk_gate(*, equity: Any, cash: Any, positions: Iterable[dict[str, Any]] | None,
                    drawdown_pct: Any, portfolio_volatility: Any = None,
                    uncertainty: Any = None, correlated_clusters: dict[str, list[str]] | None = None,
                    limits: dict[str, Any] | None = None, circuit_breaker: dict[str, Any] | None = None):
    """Block new PAPER risk when portfolio constraints cannot be proven safe."""
    lim = {**DEFAULT_RISK_LIMITS, **(limits or {})}
    eq = _safe_float(equity)
    cash_value = _safe_float(cash)
    dd = _safe_float(drawdown_pct)
    pos = list(positions or [])
    cb = circuit_breaker or {}
    malformed = []
    notionals = []
    signed = []
    sectors: dict[str, float] = {}
    symbol_values: dict[str, float] = {}
    for i, p in enumerate(pos):
        if not isinstance(p, dict):
            malformed.append(i); continue
        mv = _safe_float(p.get('market_value'))
        symbol = str(p.get('symbol') or '').strip().upper()
        sector = str(p.get('sector') or 'UNKNOWN').strip().upper()
        if mv is None or not symbol:
            malformed.append(i); continue
        notionals.append(abs(mv)); signed.append(mv)
        symbol_values[symbol] = symbol_values.get(symbol, 0.0) + abs(mv)
        sectors[sector] = sectors.get(sector, 0.0) + abs(mv)
    valid_equity = eq is not None and eq > 0
    gross = sum(notionals) / eq if valid_equity else None
    net = abs(sum(signed)) / eq if valid_equity else None
    largest = max(symbol_values.values(), default=0.0) / eq if valid_equity else None
    largest_sector = max(sectors.values(), default=0.0) / eq if valid_equity else None
    largest_cluster = 0.0 if valid_equity else None
    cluster_exposure = {}
    if valid_equity:
        for name, symbols in (correlated_clusters or {}).items():
            value = sum(symbol_values.get(str(s).upper(), 0.0) for s in symbols or [])
            pct = value / eq
            cluster_exposure[str(name)] = pct
            largest_cluster = max(largest_cluster, pct)
    cash_pct = cash_value / eq if valid_equity and cash_value is not None else None
    vol = _safe_float(portfolio_volatility)
    unc = _safe_float(uncertainty)
    checks = {
        'equity_valid': valid_equity,
        'cash_valid': cash_value is not None and cash_value >= 0,
        'positions_well_formed': not malformed,
        'gross_exposure': gross is not None and gross <= float(lim['max_gross_pct']),
        'net_exposure': net is not None and net <= float(lim['max_net_pct']),
        'single_name': largest is not None and largest <= float(lim['max_position_pct']),
        'sector_concentration': largest_sector is not None and largest_sector <= float(lim['max_sector_pct']),
        'correlated_cluster': largest_cluster is not None and largest_cluster <= float(lim['max_correlated_cluster_pct']),
        'cash_reserve': cash_pct is not None and cash_pct >= float(lim['min_cash_pct']),
        'drawdown': dd is not None and abs(dd) <= float(lim['max_drawdown_pct']),
        'volatility_known_and_bounded': vol is not None and vol <= float(lim['max_portfolio_volatility']),
        'uncertainty_known_and_bounded': unc is not None and unc <= float(lim['max_uncertainty']),
        'circuit_breaker_clear': cb.get('triggered') is False,
    }
    blockers = [k for k, v in checks.items() if not v]
    return {
        'status': 'PASS_PAPER_RISK' if not blockers else 'BLOCKED_PAPER_RISK',
        'checks': checks, 'blockers': blockers, 'limits': lim,
        'gross_pct': gross, 'net_pct': net, 'largest_position_pct': largest,
        'largest_sector_pct': largest_sector, 'largest_correlated_cluster_pct': largest_cluster,
        'cluster_exposure': cluster_exposure, 'cash_pct': cash_pct, 'drawdown_pct': dd,
        'portfolio_volatility': vol, 'uncertainty': unc,
        'new_paper_risk_allowed': not blockers, 'existing_positions_may_be_reduced': True,
        'live_execution_allowed': False, 'real_trading': False,
    }


def challenger_review_gate(*, champion: dict[str, Any] | None, challenger: dict[str, Any] | None,
                           min_forward_n: int = 40, min_forward_days: int = 14,
                           min_regimes: int = 2, min_horizons: int = 2,
                           min_net_edge: float = 0.0, max_drawdown_ratio: float = 1.25,
                           max_return_correlation: float = 0.95):
    """Recommend manual PAPER review only; never replace a champion automatically."""
    c = champion or {}; x = challenger or {}
    cn = _safe_float(c.get('mean_net_return'))
    xn = _safe_float(x.get('mean_net_return'))
    cdd = abs(_safe_float(c.get('max_drawdown_pct'), 0.0) or 0.0)
    xdd = abs(_safe_float(x.get('max_drawdown_pct'), 0.0) or 0.0)
    corr = _safe_float(x.get('return_correlation_to_champion'))
    regimes = set(x.get('forward_regimes') or [])
    horizons = set(x.get('forward_horizons') or [])
    edge = (xn - cn) if xn is not None and cn is not None else None
    checks = {
        'champion_forward_valid': c.get('forward_only') is True and c.get('backfilled') is not True,
        'challenger_forward_only': x.get('forward_only') is True and x.get('matured_only') is True,
        'no_backfill': x.get('backfilled') is not True,
        'sample_size': int(x.get('forward_n') or 0) >= int(min_forward_n),
        'forward_days': int(x.get('forward_days') or 0) >= int(min_forward_days),
        'cost_aware': x.get('cost_aware') is True,
        'benchmark_aware': x.get('benchmark_aware') is True,
        'multi_regime': len(regimes) >= int(min_regimes),
        'multi_horizon': len(horizons) >= int(min_horizons),
        'net_edge': edge is not None and edge > float(min_net_edge),
        'drawdown_stable': cdd == 0.0 or xdd <= cdd * float(max_drawdown_ratio),
        'diversity': corr is not None and abs(corr) <= float(max_return_correlation),
        'no_critical_instability': x.get('critical_instability') is not True,
    }
    blockers = [k for k, v in checks.items() if not v]
    return {
        'status': 'ELIGIBLE_FOR_MANUAL_PAPER_REVIEW' if not blockers else 'SHADOW_ONLY',
        'checks': checks, 'blockers': blockers, 'net_edge': edge,
        'automatic_replacement': False, 'automatic_promotion': False,
        'promotion_scope': 'MANUAL_REVIEW_PAPER_ONLY', 'live_execution_allowed': False,
        'historical_can_satisfy_forward_gate': False, 'real_trading': False,
    }


def abstention_disagreement_gate(signals: Iterable[dict[str, Any]] | None, *,
                                 min_confidence: float = 0.60,
                                 max_disagreement: float = 0.35,
                                 data_integrity_ok: bool = True,
                                 evidence_sufficient: bool = True):
    """Make ABSTAIN a first-class outcome when evidence quality or consensus is weak."""
    rows = [dict(x) for x in (signals or []) if isinstance(x, dict)]
    valid_actions = {'BUY', 'SELL', 'HOLD', 'ABSTAIN'}
    malformed = [i for i, x in enumerate(rows)
                 if str(x.get('action') or '').upper() not in valid_actions or _safe_float(x.get('confidence')) is None]
    confidences = [max(0.0, min(1.0, _safe_float(x.get('confidence'), 0.0))) for x in rows]
    trade_rows = [x for x in rows if str(x.get('action') or '').upper() in {'BUY', 'SELL'}]
    buy_weight = sum(_safe_float(x.get('confidence'), 0.0) for x in trade_rows if str(x.get('action')).upper() == 'BUY')
    sell_weight = sum(_safe_float(x.get('confidence'), 0.0) for x in trade_rows if str(x.get('action')).upper() == 'SELL')
    total_trade_weight = buy_weight + sell_weight
    dominant = max(buy_weight, sell_weight)
    disagreement = 1.0 - (dominant / total_trade_weight) if total_trade_weight > 0 else 1.0
    mean_conf = sum(confidences) / len(confidences) if confidences else 0.0
    reasons = []
    if not rows or malformed: reasons.append('INVALID_OR_MISSING_SIGNALS')
    if not data_integrity_ok: reasons.append('DATA_INTEGRITY_FAILURE')
    if not evidence_sufficient: reasons.append('INSUFFICIENT_EVIDENCE')
    if mean_conf < float(min_confidence): reasons.append('LOW_CONFIDENCE')
    if disagreement > float(max_disagreement): reasons.append('EXCESSIVE_DISAGREEMENT')
    if total_trade_weight <= 0: reasons.append('NO_TRADE_CONSENSUS')
    action = 'ABSTAIN' if reasons else ('BUY' if buy_weight > sell_weight else 'SELL')
    return {
        'status': 'ABSTAIN' if action == 'ABSTAIN' else 'PAPER_DECISION',
        'action': action, 'reasons': reasons, 'mean_confidence': mean_conf,
        'disagreement': disagreement, 'buy_weight': buy_weight, 'sell_weight': sell_weight,
        'journal_required': True, 'forced_trade': False,
        'live_execution_allowed': False, 'real_trading': False,
    }


def accounting_truth_gate(*, cash: Any, positions: Iterable[dict[str, Any]] | None,
                          reported_equity: Any, realized_pnl: Any, unrealized_pnl: Any,
                          reported_total_pnl: Any = None, total_costs: Any = 0.0,
                          tolerance: float = 1e-6):
    """Reconcile PAPER state without silently correcting discrepancies."""
    cv = _safe_float(cash); eq = _safe_float(reported_equity)
    rp = _safe_float(realized_pnl); up = _safe_float(unrealized_pnl)
    costs = _safe_float(total_costs)
    pos = list(positions or []); malformed=[]; market_value=0.0
    for i, p in enumerate(pos):
        if not isinstance(p, dict) or _safe_float(p.get('market_value')) is None:
            malformed.append(i); continue
        market_value += _safe_float(p.get('market_value'), 0.0)
    inputs_valid = all(x is not None for x in (cv, eq, rp, up, costs)) and not malformed
    calculated_equity = (cv + market_value) if inputs_valid else None
    equity_diff = (eq - calculated_equity) if inputs_valid else None
    total_pnl_calculated = (rp + up - costs) if inputs_valid else None
    rpt = _safe_float(reported_total_pnl) if reported_total_pnl is not None else total_pnl_calculated
    pnl_diff = (rpt - total_pnl_calculated) if inputs_valid and rpt is not None else None
    tol = abs(float(tolerance))
    checks = {
        'inputs_valid': inputs_valid,
        'cash_nonnegative': cv is not None and cv >= -tol,
        'equity_identity': equity_diff is not None and abs(equity_diff) <= tol,
        'pnl_identity': pnl_diff is not None and abs(pnl_diff) <= tol,
    }
    blockers = [k for k, v in checks.items() if not v]
    return {
        'status': 'RECONCILED' if not blockers else 'CRITICAL_RECONCILIATION_FAILURE',
        'checks': checks, 'blockers': blockers, 'market_value': market_value,
        'calculated_equity': calculated_equity, 'reported_equity': eq, 'equity_difference': equity_diff,
        'calculated_total_pnl': total_pnl_calculated, 'reported_total_pnl': rpt,
        'pnl_difference': pnl_diff, 'silent_auto_correction': False,
        'new_paper_risk_allowed': not blockers, 'live_execution_allowed': False,
        'real_trading': False,
    }


def forward_maturity_clock(intervals: Iterable[dict[str, Any]] | None, *,
                           targets: dict[str, float] | None = None):
    """Accrue only verified prospective PAPER runtime; gaps/backfill/history count zero."""
    target_hours = targets or {'72h': 72.0, '7d': 168.0, '30d': 720.0}
    valid_seconds = 0.0; accepted=[]; rejected=[]
    for idx, raw in enumerate(intervals or []):
        x = dict(raw) if isinstance(raw, dict) else {}
        start = _utc(x.get('start_at')); end = _utc(x.get('end_at'))
        duration = (end - start).total_seconds() if start is not None and end is not None and end > start else None
        checks = {
            'timestamps_valid': duration is not None,
            'prospective_paper': x.get('evidence_class') == 'PROSPECTIVE_PAPER',
            'no_backfill': x.get('backfilled') is False,
            'not_historical_or_simulated_maturity': x.get('historical') is not True and x.get('simulated_maturity') is not True,
            'runtime_healthy': x.get('runtime_healthy') is True,
            'persistence_exact': x.get('persistence_exact') is True,
            'session_continuity': x.get('session_continuity') is True,
            'data_integrity': x.get('data_integrity') is True,
            'critical_failure_absent': x.get('critical_failure') is not True,
        }
        ok = all(checks.values())
        row = {'index': idx, 'checks': checks, 'duration_seconds': max(0.0, duration or 0.0)}
        if ok:
            valid_seconds += duration; accepted.append(row)
        else:
            rejected.append(row)
    valid_hours = valid_seconds / 3600.0
    milestones = {}
    for name, hours in target_hours.items():
        reached = valid_hours >= float(hours)
        milestones[name] = {
            'status': 'PASS' if reached else 'PENDING_VALID_FORWARD_TIME',
            'required_hours': float(hours), 'valid_forward_hours': valid_hours,
            'backfill_allowed': False, 'historical_counts': False,
            'simulated_maturity_counts': False,
        }
    return {
        'status': 'VALID_FORWARD_CLOCK', 'valid_forward_hours': valid_hours,
        'accepted_intervals': accepted, 'rejected_intervals': rejected,
        'milestones': milestones, 'wall_time_is_not_maturity': True,
        'downtime_counts': False, 'backfill_allowed': False,
        'live_execution_allowed': False, 'automatic_promotion': False,
        'automatic_release': False, 'setup_1_6_allowed': False, 'real_trading': False,
    }


def priorities_8_12_gate(*, risk: dict[str, Any] | None, champion: dict[str, Any] | None,
                         abstention: dict[str, Any] | None, accounting: dict[str, Any] | None,
                         maturity: dict[str, Any] | None):
    """Composite observability gate; milestone PASS does not imply release/live authority."""
    r=risk or {}; c=champion or {}; a=abstention or {}; acc=accounting or {}; m=maturity or {}
    checks = {
        'paper_risk': r.get('status') == 'PASS_PAPER_RISK',
        'champion_challenger_governed': c.get('automatic_replacement') is False and c.get('automatic_promotion') is False,
        'abstention_supported': a.get('journal_required') is True and a.get('forced_trade') is False,
        'accounting_reconciled': acc.get('status') == 'RECONCILED',
        'forward_maturity_clock': m.get('status') == 'VALID_FORWARD_CLOCK' and m.get('backfill_allowed') is False,
    }
    blockers=[k for k,v in checks.items() if not v]
    return {
        'status':'PASS' if not blockers else 'FAIL', 'checks':checks, 'blockers':blockers,
        'paper_execution_allowed': not blockers,
        'live_execution_allowed':False, 'automatic_promotion':False,
        'automatic_release':False, 'setup_1_6_allowed':False, 'real_trading':False,
    }
