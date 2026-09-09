"""Unified read-only validation runtime v3.

Combines forward/shadow evidence, attribution, learning, degradation, global
ranking, regime state, paper execution simulation and autonomous shadow/paper
governance. No real execution path.
"""
from __future__ import annotations
from radar_validation_runtime_v2 import validation_runtime_snapshot
from radar_shadow_portfolio_v2 import shadow_portfolio_v2_status
from radar_attribution_v2 import attribution_summary
from radar_learning_loop_v2 import learn_signal_value
from radar_degradation_engine_v2 import degradation_assessment
from radar_global_opportunity_rank_v1 import rank_global_opportunities
from radar_regime_intelligence_v1 import classify_regime
from radar_promotion_governance_v2 import promotion_governance
from radar_provider_resilience_v1 import failover_order
from radar_paper_execution_v2 import simulate_fill
from radar_autonomous_loop_v1 import autonomous_cycle

REAL_TRADING=False


def _derived_paper_evidence(base_shadow, shadow_portfolio, degradation):
    s=base_shadow or {}; p=shadow_portfolio or {}
    matured=int(s.get('matured_predictions') or 0)
    benchmark_n=int(s.get('benchmark_coverage') or 0)
    cost_n=int(s.get('cost_coverage') or 0)
    return {
        'forward_days':s.get('forward_days'),
        'decisions':int(p.get('decisions') or 0),
        'marks':int(p.get('marks') or 0),
        'max_drawdown_pct':s.get('max_drawdown_pct'),
        'benchmark_coverage':(benchmark_n/matured) if matured>0 else None,
        'cost_coverage':(cost_n/matured) if matured>0 else None,
        'positive_months':int(s.get('positive_months') or 0),
        'oos_pass':bool(s.get('ledger_integrity') is True and s.get('pit_verified') is True),
        'degradation_clear':bool((degradation or {}).get('status')=='STABLE'),
        'evidence_status':'VERIFIED_FORWARD' if matured>0 else 'INSUFFICIENT_EVIDENCE',
    }


def validation_runtime_v3(*, attribution_records=None, learning_records=None,
                          degradation_reference=None, degradation_current=None,
                          cards=None, metadata_by_symbol=None, regime_snapshot=None,
                          provider_states=None, paper_evidence=None, human_paper_approval=False,
                          paper_order=None, paper_market=None, paper_assumptions=None,
                          autonomous_inputs=None):
    base=validation_runtime_snapshot()
    base_shadow=base.get('shadow') or {}
    shadow_portfolio=shadow_portfolio_v2_status()
    attribution=attribution_summary(attribution_records or [])
    learning=learn_signal_value(learning_records or [])
    degradation=degradation_assessment(degradation_reference or {}, degradation_current or {})
    ranking=rank_global_opportunities(cards or [], metadata_by_symbol or {})
    regime=classify_regime(regime_snapshot or {})
    providers=failover_order(provider_states or [])
    gate_evidence=dict(paper_evidence) if paper_evidence is not None else _derived_paper_evidence(base_shadow,shadow_portfolio,degradation)
    promotion=promotion_governance(gate_evidence, human_approved=human_paper_approval)
    if paper_order is None and paper_market is None:
        paper_execution={'status':'NOT_REQUESTED','broker_connected':False,'can_submit_order':False,'real_trading':False}
    elif promotion['paper_execution_allowed'] is not True:
        paper_execution={'status':'BLOCKED_BY_PROMOTION','reason':'shadow_gate_or_human_approval_missing',
                         'broker_connected':False,'can_submit_order':False,'real_trading':False}
    else:
        paper_execution=simulate_fill(paper_order or {},paper_market or {},paper_assumptions)
    cycle_inputs=dict(autonomous_inputs or {})
    if cycle_inputs:
        cycle_inputs['paper_review_approved']=promotion['paper_execution_allowed']
        autonomous=autonomous_cycle(cycle_inputs)
    else:
        autonomous={'status':'NOT_REQUESTED','live_execution_allowed':False,'can_trade':False,'real_trading':False}
    return {
        'runtime_version':'v3',
        'decision_lab_v5':base.get('decision_lab_v5'),
        'forward':base.get('forward'),
        'historical_lab':base.get('historical_lab'),
        'legacy_shadow_prediction_evidence':base_shadow,
        'shadow_portfolio_v2':shadow_portfolio,
        'attribution_v2':attribution,
        'learning_v2':learning,
        'degradation_v2':degradation,
        'global_opportunity_ranking_v1':ranking,
        'regime_intelligence_v1':regime,
        'provider_resilience_v1':providers,
        'paper_gate_evidence':gate_evidence,
        'shadow_to_paper_governance_v2':promotion,
        'paper_execution_v2':paper_execution,
        'autonomous_loop_v1':autonomous,
        'strategy_performance_verified':False,
        'performance_note':'NOT VERIFIED until enough immutable prospective evidence matures with benchmark and explicit costs.',
        'paper_execution_allowed':promotion['paper_execution_allowed'],
        'live_review_allowed':False,
        'live_execution_allowed':False,
        'can_trade':False,
        'auto_promote':False,
        'real_trading':False,
    }
