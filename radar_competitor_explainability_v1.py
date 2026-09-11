"""Read-only live explainability for PAPER Champion and Challengers.

This module exposes current PAPER holdings and recent decisions for UI inspection.
It does not persist league evidence, does not place orders, and cannot enable real
trading. Durable ranking/promotion authority remains in the Simulation League.
"""
from __future__ import annotations

from datetime import datetime, timezone

from radar_agents import agents_status
from radar_champion_portfolio import champion_status
from radar_simulator_league_v1 import RISK_PROFILES, DEFAULT_CHALLENGER_ORDER

REAL_TRADING = False


def _finite(value, default=0.0):
    try:
        out = float(value)
        return out if out == out and abs(out) != float('inf') else default
    except (TypeError, ValueError):
        return default


def _position(row):
    return {
        'symbol': str(row.get('symbol') or ''),
        'qty': _finite(row.get('qty')),
        'avg_price': _finite(row.get('avg_price')),
        'price': _finite(row.get('price')),
        'value': _finite(row.get('value')),
        'pnl_pct': _finite(row.get('pnl_pct')),
    }


def _decision(row):
    costs = row.get('costs')
    if costs is None:
        costs = _finite(row.get('fees')) + _finite(row.get('spread_cost')) + _finite(row.get('fx_cost'))
    gross = row.get('gross') if row.get('gross') is not None else row.get('gross_value')
    return {
        'ts': str(row.get('ts') or ''),
        'symbol': str(row.get('symbol') or ''),
        'side': str(row.get('side') or '').upper(),
        'qty': _finite(row.get('qty')),
        'price': _finite(row.get('price')),
        'value': _finite(gross),
        'costs': _finite(costs),
        'reason': str(row.get('reason') or '')[:220],
    }


def _detail(key, status):
    profile = RISK_PROFILES[key]
    equity = _finite(status.get('total'))
    invested = _finite(status.get('invested'))
    invested_pct = invested / equity * 100.0 if equity > 0 else 0.0
    return {
        'competitor_key': key,
        'display_name': profile['display_name'],
        'risk_label': profile['risk_label'],
        'strategy_kind': profile['strategy_kind'],
        'equity': equity,
        'cash': _finite(status.get('cash')),
        'invested': invested,
        'invested_pct': invested_pct,
        'pnl': _finite(status.get('pnl')),
        'pnl_pct': _finite(status.get('pnl_pct')),
        'positions': [_position(row) for row in list(status.get('positions') or [])[:8]],
        'recent_decisions': [_decision(row) for row in list(status.get('trades') or [])[:6]],
        'last_activity': str(status.get('last_step') or status.get('last_rebalance') or ''),
        'source': 'LIVE_LOCAL_PAPER_ENGINE_READ_ONLY',
        'can_trade': False,
        'real_trading': False,
    }


def competitor_live_details():
    """Return the current PAPER portfolio state for all league competitors."""
    competitors = {'champion': _detail('champion', champion_status())}
    by_key = {row.get('agent_id'): row for row in agents_status() if row.get('configured')}
    for key in DEFAULT_CHALLENGER_ORDER:
        status = by_key.get(key)
        if status:
            competitors[key] = _detail(key, status)
    return {
        'status': 'OK',
        'observed_at': datetime.now(timezone.utc).isoformat(),
        'source': 'LIVE_LOCAL_PAPER_ENGINE_READ_ONLY',
        'competitors': competitors,
        'durable_authority': False,
        'automatic_model_promotion': False,
        'live_execution_allowed': False,
        'can_trade': False,
        'real_trading': False,
    }
