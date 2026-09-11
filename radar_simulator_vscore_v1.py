"""Evidence-adjusted PAPER strategy quality score (v-score).

The v-score is a simulation monitoring metric, not a promise of future returns.
It compresses observed result quality, risk, consistency and evidence into 0..400.
Low evidence contracts the score toward neutral v200. It grants no model or live
trading authority.
"""
from __future__ import annotations

import math
import statistics
from collections import OrderedDict

from radar_core import con

REAL_TRADING = False
V_MIN = 0
V_MAX = 400
V_NEUTRAL = 200

WEIGHTS = OrderedDict((
    ('decision_quality', 0.30),
    ('risk_adjusted_return', 0.22),
    ('risk_control', 0.18),
    ('consistency', 0.12),
    ('generalization', 0.10),
    ('evidence', 0.08),
))


def clamp(value, low=0.0, high=100.0):
    return max(float(low), min(float(high), float(value)))


def _smooth_score(value, scale):
    """Map signed evidence to 0..100 around neutral 50 without hard cliffs."""
    try:
        return clamp(50.0 + 50.0 * math.tanh(float(value) / float(scale)))
    except (TypeError, ValueError, ZeroDivisionError):
        return 50.0


def _daily_values(series):
    values = []
    for row in series or []:
        if not isinstance(row, dict):
            continue
        try:
            value = float(row.get('equity'))
        except (TypeError, ValueError):
            continue
        if value > 0:
            values.append((str(row.get('date') or row.get('day') or '')[:10], value))
    return values


def _daily_returns(series):
    vals = _daily_values(series)
    out = []
    for (_, previous), (_, current) in zip(vals, vals[1:]):
        if previous > 0:
            out.append(current / previous - 1.0)
    return out


def _band(v):
    value = int(v)
    if value < 120:
        return 'MUY DEFICIENTE'
    if value < 180:
        return 'DÉBIL'
    if value < 220:
        return 'NEUTRA'
    if value < 260:
        return 'COMPETENTE'
    if value < 300:
        return 'FUERTE'
    if value < 340:
        return 'MUY FUERTE'
    return 'EXCEPCIONAL'


def compute_v_score(status, daily_series=None, trade_count=0, distinct_symbols=0,
                    target_invested_pct=70.0):
    """Return an explainable v-score from observed PAPER outcomes only.

    Generalization is deliberately a conservative proxy until regime-linked
    per-strategy evidence exists. The evidence confidence shrinks the final score
    toward v200 when the sample is small.
    """
    status = status or {}
    daily = _daily_values(daily_series)
    returns = _daily_returns(daily_series)
    observed_days = len(daily)
    moves = len(returns)
    up_days = sum(1 for r in returns if r > 1e-12)
    down_days = sum(1 for r in returns if r < -1e-12)
    directional_moves = up_days + down_days
    positive_ratio = (up_days / directional_moves) if directional_moves else 0.5

    initial = float(status.get('initial') or 0.0)
    total = float(status.get('total') or initial or 0.0)
    period_return_pct = ((total / initial) - 1.0) * 100.0 if initial > 0 else 0.0
    return_score = _smooth_score(period_return_pct, 8.0)

    sharpe = status.get('sharpe')
    if sharpe is None and len(returns) >= 3:
        sd = statistics.pstdev(returns)
        sharpe = statistics.mean(returns) / sd * math.sqrt(252.0) if sd > 1e-12 else 0.0
    try:
        sharpe = float(sharpe or 0.0)
    except (TypeError, ValueError):
        sharpe = 0.0
    sharpe_score = _smooth_score(sharpe, 2.0)

    hit_score = 100.0 * positive_ratio
    decision_quality = clamp(0.62 * hit_score + 0.38 * return_score)
    risk_adjusted_return = clamp(0.58 * return_score + 0.42 * sharpe_score)

    try:
        max_dd = float(status.get('max_drawdown_pct', status.get('drawdown_pct')) or 0.0)
    except (TypeError, ValueError):
        max_dd = 0.0
    dd_score = clamp(100.0 - abs(min(0.0, max_dd)) * 4.0)

    try:
        invested_pct = float(status.get('invested') or 0.0) / float(total) * 100.0 if total > 0 else 0.0
    except (TypeError, ValueError, ZeroDivisionError):
        invested_pct = 0.0
    target = max(1.0, float(target_invested_pct or 70.0))
    overshoot = max(0.0, invested_pct - target)
    undershoot = max(0.0, target - invested_pct)
    # Overshooting a declared risk budget is punished more than temporary under-use.
    exposure_score = clamp(100.0 - overshoot * 5.0 - undershoot * 0.35)
    risk_control = clamp(0.72 * dd_score + 0.28 * exposure_score)

    if returns:
        volatility_pct = statistics.pstdev(returns) * 100.0 if len(returns) > 1 else abs(returns[0]) * 100.0
        volatility_score = clamp(100.0 - volatility_pct * 9.0)
    else:
        volatility_score = 50.0
    consistency = clamp(0.62 * hit_score + 0.38 * volatility_score)

    # Until strategy outcomes are explicitly linked to market regimes this is only
    # a breadth proxy, intentionally capped below 80 to avoid overstating knowledge.
    breadth = min(max(int(distinct_symbols or 0), 0), 10)
    generalization = clamp(min(78.0, 42.0 + breadth * 3.0 + min(observed_days, 18) * 0.7))

    marks = int(status.get('marks') or observed_days or 0)
    trades = max(0, int(trade_count or 0))
    evidence = clamp(100.0 * (
        0.58 * min(observed_days / 20.0, 1.0) +
        0.24 * min(trades / 24.0, 1.0) +
        0.18 * min(marks / 120.0, 1.0)
    ))

    components = {
        'decision_quality': round(decision_quality, 2),
        'risk_adjusted_return': round(risk_adjusted_return, 2),
        'risk_control': round(risk_control, 2),
        'consistency': round(consistency, 2),
        'generalization': round(generalization, 2),
        'evidence': round(evidence, 2),
    }
    raw_quality = sum(components[key] * WEIGHTS[key] for key in WEIGHTS)
    confidence = clamp(0.10 + 0.90 * (evidence / 100.0), 0.10, 1.0)
    adjusted_quality = 50.0 + confidence * (raw_quality - 50.0)
    v_score = int(round(clamp(adjusted_quality) * 4.0))
    v_score = max(V_MIN, min(V_MAX, v_score))

    return {
        'v_score': v_score,
        'v_band': _band(v_score),
        'v_confidence': round(confidence, 4),
        'v_raw_quality': round(raw_quality, 2),
        'v_adjusted_quality': round(adjusted_quality, 2),
        'v_components': components,
        'observed_days': observed_days,
        'up_days': up_days,
        'down_days': down_days,
        'period_return_pct': round(period_return_pct, 4),
        'invested_pct': round(invested_pct, 4),
        'generalization_status': 'PROXY_UNTIL_REGIME_LINKAGE',
        'score_semantics': 'OBSERVED_PAPER_DECISION_QUALITY_PROXY',
        'automatic_model_promotion': False,
        'can_trade': False,
        'real_trading': False,
    }


def competitor_observations(competitor_key, status, target_invested_pct=70.0, limit=180):
    """Load local observed marks/trade breadth for one running PAPER strategy."""
    c = con()
    try:
        if competitor_key == 'champion':
            marks = c.execute(
                'select ts,total from champion_paper_marks order by id desc limit ?', (int(limit),)
            ).fetchall()
            trade_rows = c.execute(
                'select symbol from champion_paper_trades order by id desc limit 500'
            ).fetchall()
        else:
            marks = c.execute(
                'select ts,total from paper_agent_marks where agent_id=? order by id desc limit ?',
                (competitor_key, int(limit)),
            ).fetchall()
            trade_rows = c.execute(
                'select symbol from paper_agent_trades where agent_id=? order by id desc limit 500',
                (competitor_key,),
            ).fetchall()
    finally:
        c.close()
    # One final observed mark per UTC date; no synthetic/backfilled days.
    by_day = {}
    for ts, total in reversed(marks):
        day = str(ts or '')[:10]
        try:
            value = float(total)
        except (TypeError, ValueError):
            continue
        if day and value > 0:
            by_day[day] = value
    daily = [{'date': day, 'equity': value} for day, value in sorted(by_day.items())]
    symbols = {str(row[0]) for row in trade_rows if row and row[0]}
    return compute_v_score(
        status,
        daily_series=daily,
        trade_count=len(trade_rows),
        distinct_symbols=len(symbols),
        target_invested_pct=target_invested_pct,
    )
