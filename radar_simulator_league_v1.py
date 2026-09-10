"""PAPER Simulation League: one Champion plus risk-labelled Challengers.

This module only observes existing PAPER engines and sends their current state to
the durable Supabase authority. It cannot place trades and cannot promote any model
outside the Simulation League.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone

from radar_agents import agents_status
from radar_champion_portfolio import champion_status

REAL_TRADING = False
DEFAULT_LEAGUE_URL = 'https://wvmiludqzdepqmjhfwos.supabase.co/functions/v1/radar-simulator-league'
LEAGUE_URL = os.environ.get('SUPABASE_SIMULATOR_LEAGUE_URL', DEFAULT_LEAGUE_URL).strip()
SYNC_TOKEN = os.environ.get('RADAR_SYNC_TOKEN', '').strip()
NODE_ID = os.environ.get('RADAR_NODE_ID', 'cloud-primary').strip() or 'cloud-primary'
DISPLAY_BASE_EQUITY = 1000.0
PROMOTION_DAYS = 10
RISK_GUARD_PP = 10.0

RISK_PROFILES = {
    'champion': {
        'display_name': 'Champion adaptativo',
        'risk_rank': 0,
        'risk_label': 'RIESGO BASE · ADAPTATIVO',
        'target_invested_pct': 70.0,
        'strategy_kind': 'CHAMPION_ADAPTIVE',
    },
    'conservative': {
        'display_name': 'Conservador',
        'risk_rank': -2,
        'risk_label': 'RIESGO --',
        'target_invested_pct': 55.0,
        'strategy_kind': 'CHALLENGER_RISK_MINUS_MINUS',
    },
    'balanced': {
        'display_name': 'Equilibrado',
        'risk_rank': -1,
        'risk_label': 'RIESGO -',
        'target_invested_pct': 70.0,
        'strategy_kind': 'CHALLENGER_RISK_MINUS',
    },
    'aggressive': {
        'display_name': 'Agresivo',
        'risk_rank': 1,
        'risk_label': 'RIESGO +',
        'target_invested_pct': 82.0,
        'strategy_kind': 'CHALLENGER_RISK_PLUS',
    },
    'high_conviction': {
        'display_name': 'Alta convicción',
        'risk_rank': 2,
        'risk_label': 'RIESGO ++',
        'target_invested_pct': 90.0,
        'strategy_kind': 'CHALLENGER_RISK_PLUS_PLUS',
    },
    'experimental': {
        'display_name': 'Experimental',
        'risk_rank': 3,
        'risk_label': 'RIESGO +++ · EXP',
        'target_invested_pct': 92.0,
        'strategy_kind': 'CHALLENGER_EXPERIMENTAL',
    },
}

DEFAULT_CHALLENGER_ORDER = [
    'conservative', 'balanced', 'aggressive', 'high_conviction', 'experimental'
]


def normalize_equity(equity, initial_equity, base=DISPLAY_BASE_EQUITY):
    """Convert different PAPER account sizes to a comparable 1,000-euro baseline."""
    try:
        equity = float(equity)
        initial = float(initial_equity)
        base = float(base)
    except (TypeError, ValueError):
        return None
    if initial <= 0 or equity < 0 or base <= 0:
        return None
    return equity / initial * base


def daily_move_counts(series):
    """Count equity up/down observations; these are UI 'hits/errors', not forecast accuracy."""
    values = []
    for row in series or []:
        try:
            values.append(float(row.get('normalized_equity', row.get('equity'))))
        except (AttributeError, TypeError, ValueError):
            continue
    up = down = neutral = 0
    for previous, current in zip(values, values[1:]):
        if current > previous:
            up += 1
        elif current < previous:
            down += 1
        else:
            neutral += 1
    return {'up_days': up, 'down_days': down, 'neutral_days': neutral}


def consecutive_lead_days(challenger, champion):
    """Count consecutive latest common weekdays with challenger equity above Champion."""
    c = {str(r.get('date') or r.get('day'))[:10]: r for r in challenger or []}
    h = {str(r.get('date') or r.get('day'))[:10]: r for r in champion or []}
    common = []
    for day in sorted(set(c) & set(h)):
        try:
            dt = datetime.fromisoformat(day).replace(tzinfo=timezone.utc)
            cv = float(c[day].get('normalized_equity', c[day].get('equity')))
            hv = float(h[day].get('normalized_equity', h[day].get('equity')))
        except (TypeError, ValueError):
            continue
        if dt.weekday() < 5:
            common.append((day, cv, hv))
    streak = 0
    for _day, cv, hv in reversed(common):
        if cv > hv:
            streak += 1
        else:
            break
    return streak


def promotion_candidate(streak, challenger_drawdown, champion_drawdown,
                        promotion_days=PROMOTION_DAYS, risk_guard_pp=RISK_GUARD_PP):
    """Simulation-only promotion gate. No model/live authority is granted."""
    streak = max(0, int(streak or 0))
    try:
        challenger_dd = float(challenger_drawdown or 0.0)
        champion_dd = float(champion_drawdown or 0.0)
    except (TypeError, ValueError):
        challenger_dd = champion_dd = 0.0
    risk_ok = challenger_dd >= champion_dd - float(risk_guard_pp)
    remaining = max(0, int(promotion_days) - streak)
    return {
        'streak_days': streak,
        'required_days': int(promotion_days),
        'days_remaining': remaining,
        'risk_guard_ok': risk_ok,
        'eligible': streak >= int(promotion_days) and risk_ok,
        'promotion_scope': 'SIMULATION_LEAGUE_ONLY',
        'automatic_model_promotion': False,
        'can_trade': False,
        'real_trading': False,
    }


def _competitor_row(key, status):
    profile = RISK_PROFILES[key]
    initial = status.get('initial')
    equity = status.get('total')
    normalized = normalize_equity(equity, initial)
    invested = status.get('invested')
    invested_pct = None
    try:
        if float(equity) > 0:
            invested_pct = float(invested or 0.0) / float(equity) * 100.0
    except (TypeError, ValueError):
        pass
    return {
        'competitor_key': key,
        'display_name': profile['display_name'],
        'risk_rank': profile['risk_rank'],
        'risk_label': profile['risk_label'],
        'strategy_kind': profile['strategy_kind'],
        'initial_equity': initial,
        'equity': equity,
        'normalized_equity': normalized,
        'cash': status.get('cash'),
        'invested': invested,
        'invested_pct': invested_pct,
        'target_invested_pct': profile['target_invested_pct'],
        'drawdown_pct': status.get('max_drawdown_pct', status.get('drawdown_pct')),
        'observed_at': datetime.now(timezone.utc).isoformat(),
        'real_trading': False,
    }


def current_competitors():
    """Observe the six genuinely running PAPER strategies."""
    rows = [_competitor_row('champion', champion_status())]
    by_key = {row.get('agent_id'): row for row in agents_status() if row.get('configured')}
    for key in DEFAULT_CHALLENGER_ORDER:
        status = by_key.get(key)
        if status:
            rows.append(_competitor_row(key, status))
    return rows


def _post(payload, timeout=40):
    if not (LEAGUE_URL and SYNC_TOKEN):
        return {'ok': False, 'status': 'AUTHORITY_DISABLED', 'real_trading': False}
    data = json.dumps(payload, ensure_ascii=False, default=str).encode('utf-8')
    req = urllib.request.Request(
        LEAGUE_URL, data=data, method='POST',
        headers={
            'Content-Type': 'application/json',
            'X-Radar-Token': SYNC_TOKEN,
            'User-Agent': 'RadarSimulationLeague/1.0',
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return json.loads(response.read().decode('utf-8'))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode('utf-8', 'replace')
        raise RuntimeError(f'simulation league HTTP {exc.code}: {body[:1000]}') from exc


def push_league_snapshot():
    payload = {
        'action': 'persist_simulator_league',
        'node_id': NODE_ID,
        'competitors': current_competitors(),
        'default_champion_key': 'champion',
        'challenger_order': DEFAULT_CHALLENGER_ORDER,
        'promotion_days': PROMOTION_DAYS,
        'risk_guard_pp': RISK_GUARD_PP,
        'display_base_equity': DISPLAY_BASE_EQUITY,
        'real_trading': False,
    }
    out = _post(payload)
    out['real_trading'] = False
    return out


def league_status(days=30):
    window = max(1, min(int(days or 30), 90))
    out = _post({
        'action': 'simulator_league',
        'node_id': NODE_ID,
        'days': window,
        'display_base_equity': DISPLAY_BASE_EQUITY,
        'real_trading': False,
    })
    out['real_trading'] = False
    return out
