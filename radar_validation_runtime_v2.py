"""Read-only runtime view for Part II validation evidence."""
from __future__ import annotations
from radar_shadow_experiment_v2 import shadow_experiment_evidence
from radar_promotion_attribution_v1 import promotion_gate
from radar_forward_engine import forward_health
from radar_historical_lab import historical_lab_health

REAL_TRADING=False


def validation_runtime_snapshot():
    shadow=shadow_experiment_evidence()
    promotion=promotion_gate({k:shadow.get(k) for k in (
        'forward_days','matured_predictions','decisions','max_drawdown_pct','brier','hit_rate',
        'excess_return_pct','positive_months','ledger_integrity','pit_verified','costs_included')})
    return {
        'shadow':shadow,
        'promotion':promotion,
        'forward':forward_health(),
        'historical_lab':historical_lab_health(8),
        'ready_for_live_review':promotion['ready_for_live_review'],
        'can_trade':False,
        'auto_promote':False,
        'real_trading':False,
    }
