"""PAPER Simulation League: Champion plus risk-labelled Challengers.

The league observes existing PAPER engines, calculates an evidence-adjusted v-score,
and sends current state to durable Supabase authority. Promotion is dynamic and
limited to the Simulation League. It cannot place trades or promote production models.
"""
from __future__ import annotations

import json
import math
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone

from radar_agents import agents_status
from radar_champion_portfolio import champion_status
from radar_simulator_vscore_v1 import competitor_observations

REAL_TRADING = False
DEFAULT_LEAGUE_URL = 'https://wvmiludqzdepqmjhfwos.supabase.co/functions/v1/radar-simulator-league'
LEAGUE_URL = os.environ.get('SUPABASE_SIMULATOR_LEAGUE_URL', DEFAULT_LEAGUE_URL).strip()
SYNC_TOKEN = os.environ.get('RADAR_SYNC_TOKEN', '').strip()
NODE_ID = os.environ.get('RADAR_NODE_ID', 'cloud-primary').strip() or 'cloud-primary'
DISPLAY_BASE_EQUITY = 1000.0
RISK_GUARD_PP = 10.0
PROMOTION_THRESHOLD = 88.0
MIN_PROMOTION_CONFIDENCE = 0.55
MIN_V_ADVANTAGE = 4.0
PROMOTION_POLICY_VERSION = 'dynamic_v1'

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
    try:
        equity = float(equity); initial = float(initial_equity); base = float(base)
    except (TypeError, ValueError):
        return None
    if initial <= 0 or equity < 0 or base <= 0:
        return None
    return equity / initial * base


def daily_move_counts(series):
    """Count equity up/down observations; UI hits/errors, not prediction accuracy."""
    values = []
    for row in series or []:
        try: values.append(float(row.get('normalized_equity', row.get('equity'))))
        except (AttributeError, TypeError, ValueError): continue
    up = down = neutral = 0
    for previous, current in zip(values, values[1:]):
        if current > previous: up += 1
        elif current < previous: down += 1
        else: neutral += 1
    return {'up_days': up, 'down_days': down, 'neutral_days': neutral}


def consecutive_lead_days(challenger, champion):
    """Compatibility diagnostic only; no longer the promotion rule."""
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
        if dt.weekday() < 5: common.append((day, cv, hv))
    streak = 0
    for _day, cv, hv in reversed(common):
        if cv > hv: streak += 1
        else: break
    return streak


def dynamic_required_days(v_gap, confidence, equity_gap_pct=0.0):
    """Evidence horizon chosen from advantage magnitude and confidence, not a fixed rule."""
    try:
        gap = float(v_gap); conf = max(0.0, min(1.0, float(confidence))); equity_gap = float(equity_gap_pct)
    except (TypeError, ValueError):
        gap, conf, equity_gap = 0.0, 0.0, 0.0
    days = 4.0 + (1.0 - conf) * 18.0 + max(0.0, 10.0 - gap) * 0.65 + max(0.0, 1.5 - equity_gap) * 1.5
    return max(2, min(30, int(math.ceil(days))))


def promotion_candidate(readiness, challenger_drawdown, champion_drawdown, *, v_gap=0.0,
                        confidence=0.0, equity_gap_pct=0.0, common_days=0,
                        risk_guard_pp=RISK_GUARD_PP,
                        threshold=PROMOTION_THRESHOLD):
    """Reference dynamic promotion gate; actual durable decision is repeated in Edge."""
    try:
        challenger_dd = float(challenger_drawdown or 0.0); champion_dd = float(champion_drawdown or 0.0)
    except (TypeError, ValueError):
        challenger_dd = champion_dd = 0.0
    risk_ok = challenger_dd >= champion_dd - float(risk_guard_pp)
    required = dynamic_required_days(v_gap, confidence, equity_gap_pct)
    evidence_ok = int(common_days or 0) >= required
    quality_ok = float(v_gap or 0.0) >= MIN_V_ADVANTAGE
    confidence_ok = float(confidence or 0.0) >= MIN_PROMOTION_CONFIDENCE
    eligible = (
        float(readiness or 0.0) >= float(threshold) and risk_ok and evidence_ok and quality_ok and
        confidence_ok and float(equity_gap_pct or 0.0) > 0.0
    )
    return {
        'readiness': round(float(readiness or 0.0), 2),
        'threshold': float(threshold),
        'v_gap': round(float(v_gap or 0.0), 2),
        'confidence': round(float(confidence or 0.0), 4),
        'common_days': int(common_days or 0),
        'dynamic_required_days': required,
        'risk_guard_ok': risk_ok,
        'evidence_ok': evidence_ok,
        'quality_ok': quality_ok,
        'confidence_ok': confidence_ok,
        'eligible': eligible,
        'promotion_policy': PROMOTION_POLICY_VERSION,
        'promotion_scope': 'SIMULATION_LEAGUE_ONLY',
        'automatic_model_promotion': False,
        'can_trade': False,
        'real_trading': False,
    }


def _competitor_row(key, status):
    profile = RISK_PROFILES[key]
    initial = status.get('initial'); equity = status.get('total')
    normalized = normalize_equity(equity, initial)
    invested = status.get('invested'); invested_pct = None
    try:
        if float(equity) > 0: invested_pct = float(invested or 0.0) / float(equity) * 100.0
    except (TypeError, ValueError): pass
    quality = competitor_observations(key, status, profile['target_invested_pct'])
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
        'v_score': quality['v_score'],
        'v_band': quality['v_band'],
        'v_confidence': quality['v_confidence'],
        'v_raw_quality': quality['v_raw_quality'],
        'v_components': quality['v_components'],
        'v_generalization_status': quality['generalization_status'],
        'observed_at': datetime.now(timezone.utc).isoformat(),
        'score_semantics': quality['score_semantics'],
        'automatic_model_promotion': False,
        'can_trade': False,
        'real_trading': False,
    }


def current_competitors():
    rows = [_competitor_row('champion', champion_status())]
    by_key = {row.get('agent_id'): row for row in agents_status() if row.get('configured')}
    for key in DEFAULT_CHALLENGER_ORDER:
        status = by_key.get(key)
        if status: rows.append(_competitor_row(key, status))
    return rows


def _post(payload, timeout=40):
    if not (LEAGUE_URL and SYNC_TOKEN):
        return {'ok': False, 'status': 'AUTHORITY_DISABLED', 'real_trading': False}
    data = json.dumps(payload, ensure_ascii=False, default=str).encode('utf-8')
    req = urllib.request.Request(
        LEAGUE_URL, data=data, method='POST',
        headers={'Content-Type':'application/json','X-Radar-Token':SYNC_TOKEN,'User-Agent':'RadarSimulationLeague/2.0'},
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
        'promotion_threshold': PROMOTION_THRESHOLD,
        'min_promotion_confidence': MIN_PROMOTION_CONFIDENCE,
        'min_v_advantage': MIN_V_ADVANTAGE,
        'risk_guard_pp': RISK_GUARD_PP,
        'promotion_policy': PROMOTION_POLICY_VERSION,
        'display_base_equity': DISPLAY_BASE_EQUITY,
        'real_trading': False,
    }
    out = _post(payload); out['real_trading'] = False; return out


def league_status(days=30):
    window = max(1, min(int(days or 30), 90))
    out = _post({
        'action': 'simulator_league','node_id': NODE_ID,'days': window,
        'display_base_equity': DISPLAY_BASE_EQUITY,'real_trading': False,
    })
    out['real_trading'] = False
    return out
