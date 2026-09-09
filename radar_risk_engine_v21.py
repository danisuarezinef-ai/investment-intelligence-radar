"""Risk Engine v2.1: volatility + regime-aware fail-closed portfolio gating."""
from __future__ import annotations

from radar_risk_engine_v2 import DEFAULT_LIMITS as V2_LIMITS, risk_gate_v2

REAL_TRADING = False

DEFAULT_LIMITS = dict(V2_LIMITS, max_annualized_vol_pct=55.0, soft_annualized_vol_pct=35.0,
                      min_regime_risk_multiplier=0.35)


def _f(x):
    try: return float(x)
    except (TypeError, ValueError): return None


def risk_gate_v21(portfolio, proposal, metadata=None, correlations=None, regime=None, limits=None):
    l = dict(DEFAULT_LIMITS); l.update(limits or {})
    metadata = dict(metadata or {})
    base = risk_gate_v2(portfolio, proposal, metadata=metadata, correlations=correlations, limits=l)
    blockers = list(base.get('blockers') or [])
    warnings = list(base.get('warnings') or [])
    vol = _f(metadata.get('annualized_vol_pct'))
    regime = regime or {}
    regime_mult = _f(regime.get('risk_multiplier'))
    regime_state = str(regime.get('state') or regime.get('regime') or 'UNKNOWN').upper()

    if vol is None:
        blockers.append('volatility_evidence_missing')
    elif vol > float(l['max_annualized_vol_pct']):
        blockers.append('volatility_hard_stop')
    elif vol > float(l['soft_annualized_vol_pct']):
        warnings.append('high_volatility_reduction')

    if regime_mult is None:
        blockers.append('regime_evidence_missing')
        regime_mult = 0.0
    elif regime_mult < float(l['min_regime_risk_multiplier']):
        blockers.append('regime_risk_floor')

    multiplier = float(base.get('risk_multiplier') or 0.0)
    if vol is not None and vol > float(l['soft_annualized_vol_pct']):
        span = max(1.0, float(l['max_annualized_vol_pct']) - float(l['soft_annualized_vol_pct']))
        multiplier *= max(0.25, 1.0 - 0.5 * ((vol - float(l['soft_annualized_vol_pct'])) / span))
    multiplier *= max(0.0, min(1.0, regime_mult))

    requested_allowed = float(base.get('allowed_budget') or 0.0)
    allowed = requested_allowed * (multiplier / float(base.get('risk_multiplier') or 1.0)) if requested_allowed else 0.0
    if blockers: allowed = 0.0
    return {
        **base,
        'blocked': allowed <= 0,
        'allowed_budget': max(0.0, allowed),
        'risk_multiplier': multiplier,
        'annualized_vol_pct': vol,
        'regime_state': regime_state,
        'regime_risk_multiplier': regime_mult,
        'blockers': sorted(set(blockers)),
        'warnings': sorted(set(warnings)),
        'limits': l,
        'policy_note': 'volatility/regime limits are conservative policy defaults; NOT empirically validated as optimal',
        'can_trade': False,
        'real_trading': False,
    }
